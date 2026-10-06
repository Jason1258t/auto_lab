"""LLM manager (drafts/llm_manager.md).

Every model request goes through here. There is one in-memory queue per
model and one consumer per queue, so a model runs one call at a time
(one small GPU). Each call is one llm_calls row; the full prompt and
answer go to the log store under the same id.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jsonschema
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import LlmCall, LlmResponse, Model, ModelProvider, Task
from autolab.db.models.enums import LlmCallStatus, TaskStatus
from autolab.logstore import LogStore
from autolab.worker.gateway import Adapter, GatewayError, GenerateRequest, Message

log = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]


class TaskCancelled(Exception):
    """The task was cancelled while the worker was busy with it."""


class LlmCallFailed(Exception):
    """The provider could not answer. The message is safe for users."""


@dataclass(frozen=True)
class CallResult:
    call_id: int
    text: str
    # The parsed answer if a schema was given and the answer matches it;
    # None otherwise (the caller may try again).
    data: dict[str, Any] | None


@dataclass
class _Job:
    call_id: int
    task_id: int
    messages: list[Message]
    schema: dict[str, Any] | None
    params: dict[str, Any]
    future: asyncio.Future


def parse_answer(text: str, schema: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool]:
    """Returns (data, valid). Without a schema there is nothing to check."""
    if schema is None:
        return None, True
    try:
        data = json.loads(text)
        jsonschema.validate(data, schema)
    except (ValueError, jsonschema.ValidationError):
        return None, False
    return data, True


class LlmManager:
    def __init__(
        self, session_factory: SessionFactory, log_store: LogStore, adapters: dict[str, Adapter]
    ) -> None:
        self.session_factory = session_factory
        self.log_store = log_store
        self.adapters = adapters
        self.queues: dict[int, asyncio.Queue[_Job]] = {}
        self.consumers: dict[int, asyncio.Task] = {}

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

        request = GenerateRequest(
            model=model.name,
            base_url=model.base_url or provider.base_url,
            messages=job.messages,
            schema=job.schema,
            params=job.params,
        )
        await self._set_status(job.call_id, LlmCallStatus.RUNNING, started_at=datetime.now(UTC))
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
        job.future.set_result(CallResult(job.call_id, result.text, data))

    async def close(self) -> None:
        for consumer in self.consumers.values():
            consumer.cancel()
        await asyncio.gather(*self.consumers.values(), return_exceptions=True)
