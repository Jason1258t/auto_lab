"""LLM manager (drafts/llm_manager.md).

Every model request goes through here. There is one in-memory queue per
model and one consumer per queue, so a model runs one call at a time
(one small GPU). Each call is one llm_calls row; the full prompt and
answer go to the log store under the same id.
"""

import asyncio
import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jsonschema
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import LlmCall, LlmResponse, Model, ModelProvider, Task
from autolab.db.models.enums import FinishReason, LlmCallStatus, TaskStatus
from autolab.logstore import LogStore
from autolab.worker.gateway import (
    Adapter,
    GatewayError,
    GenerateRequest,
    GenerateResult,
    Message,
)

log = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]

# Window guard (drafts/token_budgets.md, phase 1). We do not have the
# model's tokenizer, so the prompt size is an estimate; 3.5 characters per
# token is a careful guess for English and code (Russian is denser).
CHARS_PER_TOKEN = 3.5
TOKENS_PER_MESSAGE = 10  # the chat template around each message
MIN_ANSWER_TOKENS = 64  # less room than this: do not even try
DEFAULT_REASONING_TOKENS = 1024  # models.reasoning_tokens is NULL

# Per-call timeout (phase 1, item 3): expected time x 2, plus time to load
# the model into memory (a 12 GB model takes about a minute from disk).
TIMEOUT_FACTOR = 2.0
LOAD_SECONDS = 120.0
SPEED_WEIGHT = 0.3  # how much one new call changes the learned speed


class TaskCancelled(Exception):
    """The task was cancelled while the worker was busy with it."""


class LlmCallFailed(Exception):
    """The provider could not answer. The message is safe for users."""


class PromptTooLong(LlmCallFailed):
    """The prompt leaves no room for an answer in the model's window.
    Trying again with the same prompt cannot help."""


@dataclass(frozen=True)
class CallResult:
    call_id: int
    text: str
    # The parsed answer if a schema was given and the answer matches it;
    # None otherwise (the caller may try again).
    data: dict[str, Any] | None
    finish_reason: FinishReason


@dataclass
class _Job:
    call_id: int
    task_id: int
    messages: list[Message]
    schema: dict[str, Any] | None
    params: dict[str, Any]
    future: asyncio.Future


@dataclass
class Speed:
    """A model's measured speed in tokens per second, learned from the
    calls of this worker process (none yet after a start)."""

    prompt: float | None = None
    output: float | None = None

    def learn(self, result: GenerateResult) -> None:
        if result.input_tokens and result.prompt_seconds:
            self.prompt = average(self.prompt, result.input_tokens / result.prompt_seconds)
        if result.output_tokens and result.output_seconds:
            self.output = average(self.output, result.output_tokens / result.output_seconds)

    def timeout(self, prompt_tokens: int, max_tokens: int | None) -> float | None:
        """None while the speed is unknown: the adapter's own timeout."""
        if self.prompt is None or self.output is None or max_tokens is None:
            return None
        expected = prompt_tokens / self.prompt + max_tokens / self.output
        return TIMEOUT_FACTOR * expected + LOAD_SECONDS


def average(old: float | None, new: float) -> float:
    return new if old is None else (1 - SPEED_WEIGHT) * old + SPEED_WEIGHT * new


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


def estimate_tokens(messages: list[Message]) -> int:
    """A rough prompt size in tokens, from the length of the text."""
    chars = sum(len(m.content) for m in messages)
    return math.ceil(chars / CHARS_PER_TOKEN) + TOKENS_PER_MESSAGE * len(messages)


def add_model_budget(params: dict[str, Any], model: Model) -> dict[str, Any]:
    """max_tokens in a pipeline file is the answer size. A thinking model
    (a *_think class) gets extra room to think before the answer; the
    model's own output cap is the upper bound (token_budgets.md, phase 2)."""
    if "max_tokens" not in params:
        return params
    limit = params["max_tokens"]
    if model.size_class.thinks:
        limit += model.reasoning_tokens or DEFAULT_REASONING_TOKENS
    if model.max_output_tokens is not None:
        limit = min(limit, model.max_output_tokens)
    return {**params, "max_tokens": limit}


def fit_to_window(
    params: dict[str, Any], prompt_tokens: int, context_length: int
) -> dict[str, Any]:
    """Lower max_tokens so that prompt + answer fit the window. Without
    this Ollama silently cuts the prompt. Raises PromptTooLong if there is
    no useful room left."""
    room = context_length - prompt_tokens
    if room < MIN_ANSWER_TOKENS:
        raise PromptTooLong(
            f"The prompt is too long for the model's window "
            f"(about {prompt_tokens} tokens of {context_length})"
        )
    if "max_tokens" in params and params["max_tokens"] > room:
        return {**params, "max_tokens": room}
    return params


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
