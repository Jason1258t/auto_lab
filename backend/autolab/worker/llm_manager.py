"""LLM manager (drafts/llm_manager.md).

Every model request goes through here. There is one in-memory queue per
model and one consumer per queue, so a model runs one call at a time
(one small GPU). Each call is one llm_calls row; the full prompt and
answer go to the log store under the same id.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import LlmCall, LlmResponse, Model, ModelProvider, Task
from autolab.db.models.enums import LlmCallStatus, TaskStatus
from autolab.logstore import LogStore
from autolab_engine.budget import Speed, add_model_budget, estimate_tokens, fit_to_window
from autolab_engine.gateway import Adapter, GatewayError, GenerateRequest, Message
from autolab_engine.llm import CallResult, LlmCallFailed, PromptTooLong, parse_answer

log = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]


class TaskCancelled(Exception):
    """The task was cancelled while the worker was busy with it."""


@dataclass
class _Job:
    call_id: int
    task_id: int
    messages: list[Message]
    schema: dict[str, Any] | None
    params: dict[str, Any]
    future: asyncio.Future


class LlmManager:
    def __init__(
        self, session_factory: SessionFactory, log_store: LogStore, adapters: dict[str, Adapter]
    ) -> None:
        self.session_factory = session_factory
        self.log_store = log_store
        self.adapters = adapters
        self.queues: dict[int, asyncio.Queue[_Job]] = {}
        self.consumers: dict[int, asyncio.Task] = {}
        self.speeds: dict[int, Speed] = {}  # by model id

    async def recover(self) -> int:
        """At start: queues were in memory, so calls left as queued or
        running are lost. Mark them failed; the step may try again."""
        async with self.session_factory() as db:
            result = await db.execute(
                update(LlmCall)
                .where(LlmCall.status.in_([LlmCallStatus.QUEUED, LlmCallStatus.RUNNING]))
                .values(status=LlmCallStatus.FAILED, error="manager restarted")
            )
            await db.commit()
            return result.rowcount

    async def call(
        self,
        *,
        task_id: int,
        step_index: int,
        model_id: int,
        messages: list[Message],
        schema: dict[str, Any] | None,
        params: dict[str, Any],
        attempt: int,
    ) -> CallResult:
        """Queue one request and wait for its answer."""
        async with self.session_factory() as db:
            call = LlmCall(
                task_id=task_id,
                step_index=step_index,
                model_id=model_id,
                attempt=attempt,
                response_schema=schema,
                params=params,
            )
            db.add(call)
            await db.commit()
            call_id = call.id

        future = asyncio.get_running_loop().create_future()
        await self._queue(model_id).put(_Job(call_id, task_id, messages, schema, params, future))
        return await future

    def _queue(self, model_id: int) -> asyncio.Queue[_Job]:
        if model_id not in self.queues:
            self.queues[model_id] = asyncio.Queue()
            self.consumers[model_id] = asyncio.create_task(self._consume(model_id))
        return self.queues[model_id]

    def queue_lengths(self) -> dict[int, int]:
        """Live load per model (for a later admin page)."""
        return {model_id: queue.qsize() for model_id, queue in self.queues.items()}

    async def _consume(self, model_id: int) -> None:
        queue = self.queues[model_id]
        while True:
            job = await queue.get()
            try:
                await self._run(model_id, job)
            except Exception:  # never let one bad call stop the queue
                log.exception("LLM call %s crashed", job.call_id)
                await self._set_status(job.call_id, LlmCallStatus.FAILED, error="internal error")
                if not job.future.done():
                    job.future.set_exception(LlmCallFailed("internal error"))
            finally:
                queue.task_done()

    async def _set_status(self, call_id: int, status: LlmCallStatus, **values: Any) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(LlmCall).where(LlmCall.id == call_id).values(status=status, **values)
            )
            await db.commit()

    async def _run(self, model_id: int, job: _Job) -> None:
        async with self.session_factory() as db:
            task_status = await db.scalar(select(Task.status).where(Task.id == job.task_id))
            row = (
                await db.execute(
                    select(Model, ModelProvider)
                    .join(ModelProvider, ModelProvider.id == Model.provider_id)
                    .where(Model.id == model_id)
                )
            ).one()
        model, provider = row

        # Cancelled while waiting in the queue: do not run it.
        if task_status == TaskStatus.CANCELLED:
            await self._set_status(job.call_id, LlmCallStatus.CANCELLED)
            job.future.set_exception(TaskCancelled())
            return

        adapter = self.adapters.get(provider.adapter)
        if adapter is None:
            message = f"no adapter for provider '{provider.name}' ({provider.adapter}) yet"
            await self._set_status(job.call_id, LlmCallStatus.FAILED, error=message)
            job.future.set_exception(LlmCallFailed(message))
            return

        prompt_tokens = estimate_tokens(job.messages)
        try:
            params = fit_to_window(
                add_model_budget(job.params, model), prompt_tokens, model.context_length
            )
        except PromptTooLong as exc:
            await self._set_status(job.call_id, LlmCallStatus.FAILED, error=str(exc))
            job.future.set_exception(exc)
            return

        request = GenerateRequest(
            model=model.name,
            base_url=model.base_url or provider.base_url,
            messages=job.messages,
            schema=job.schema,
            # The context window from the catalog. Without it Ollama uses
            # its own default and silently cuts longer prompts.
            params={**params, "context_length": model.context_length},
            timeout_seconds=self.speeds.setdefault(model_id, Speed()).timeout(
                prompt_tokens, params.get("max_tokens")
            ),
        )
        # The row keeps the limit really sent (it may be lower than asked).
        await self._set_status(
            job.call_id, LlmCallStatus.RUNNING, started_at=datetime.now(UTC), params=params
        )
        await self.log_store.create(job.call_id, request.as_log())

        try:
            result = await adapter.generate(request)
        except GatewayError as exc:
            # Full error in the system log, a short safe one in the DB.
            log.warning("LLM call %s (task %s) failed: %s", job.call_id, job.task_id, exc)
            await self._set_status(
                job.call_id,
                LlmCallStatus.FAILED,
                error="The model did not answer",
                finished_at=datetime.now(UTC),
            )
            job.future.set_exception(LlmCallFailed("The model did not answer"))
            return

        self.speeds[model_id].learn(result)
        await self.log_store.add_response(job.call_id, {"text": result.text, "raw": result.raw})
        data, valid = parse_answer(result.text, job.schema)
        async with self.session_factory() as db:
            # The response row and status 'done' together (schema_design.md,
            # "Normalization": done <=> a response row exists).
            db.add(
                LlmResponse(
                    call_id=job.call_id,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    finish_reason=result.finish_reason,
                    valid_json=valid if job.schema is not None else None,
                )
            )
            await db.execute(
                update(LlmCall)
                .where(LlmCall.id == job.call_id)
                .values(status=LlmCallStatus.DONE, finished_at=datetime.now(UTC))
            )
            await db.commit()
        job.future.set_result(CallResult(job.call_id, result.text, data, result.finish_reason))

    async def close(self) -> None:
        for consumer in self.consumers.values():
            consumer.cancel()
        await asyncio.gather(*self.consumers.values(), return_exceptions=True)


@dataclass
class TaskLlm:
    """The engine's LlmClient for one task: every call goes through the
    manager (its queue, llm_calls rows and the log store)."""

    manager: LlmManager
    task_id: int
    model_id: int

    async def call(
        self,
        *,
        step_index: int,
        messages: list[Message],
        schema: dict[str, Any] | None,
        params: dict[str, Any],
        attempt: int,
    ) -> CallResult:
        return await self.manager.call(
            task_id=self.task_id,
            step_index=step_index,
            model_id=self.model_id,
            messages=messages,
            schema=schema,
            params=params,
            attempt=attempt,
        )
