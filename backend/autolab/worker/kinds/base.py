"""What a step kind gets to do its work (drafts/pipeline_spec.md, 4-6)."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from autolab.config import Settings
from autolab.db.models import Task
from autolab.worker import templates
from autolab.worker.gateway import Message
from autolab.worker.llm_manager import LlmCallFailed, LlmManager
from autolab.worker.pipelines import PipelineFile, Step
from autolab.worker.web import Resolver

log = logging.getLogger(__name__)


class StepFailed(Exception):
    """The step cannot finish. The message goes into the step summary,
    so it must be short and safe for users."""


@dataclass
class StepContext:
    task: Task
    pipeline: PipelineFile
    step: Step
    step_index: int
    outputs: dict[str, dict[str, Any]]  # outputs of earlier steps, by step id
    llm: LlmManager
    settings: Settings
    http: httpx.AsyncClient | None = None  # for search and fetch
    resolver: Resolver | None = None  # host name -> addresses (fetch)
    note: str | None = None  # revise note, added to every prompt (later step)
    skipped: int = field(default=0)  # for_each items without a valid answer

    def resolve(self, ref: str) -> Any:
        """'<step id>.<field>' -> that field of the earlier step's output."""
        step_id, _, name = ref.partition(".")
        try:
            return self.outputs[step_id][name]
        except KeyError as exc:
            raise StepFailed(f"no '{ref}' in the output of step '{step_id}'") from exc

    def variables(self, **extra: Any) -> dict[str, Any]:
        found = {
            "task": {"title": self.task.title, "input": self.task.input},
            "config": self.step.config,
        }
        if self.step.from_:
            found["input"] = self.resolve(self.step.from_)
        return found | extra

    def messages(self, variables: dict[str, Any]) -> list[Message]:
        llm = self.step.llm
        prompt = templates.render(llm.prompt, variables)
        if self.note:
            prompt += "\n\n" + self.note
        found = [Message("system", templates.render(llm.system, variables))] if llm.system else []
        return found + [Message("user", prompt)]

    async def ask(self, **extra: Any) -> dict[str, Any] | None:
        """One model answer that matches the output schema, trying up to
        max_attempts times. None if no attempt gave a valid answer."""
        llm = self.step.llm
        messages = self.messages(self.variables(**extra))
        for attempt in range(1, llm.max_attempts + 1):
            try:
                result = await self.llm.call(
                    task_id=self.task.id,
                    step_index=self.step_index,
                    model_id=self.task.model_id,
                    messages=messages,
                    schema=llm.output,
                    params={"temperature": llm.temperature, "max_tokens": llm.max_tokens},
                    attempt=attempt,
                )
            except LlmCallFailed:
                continue
            if result.data is not None:
                return result.data
            log.info(
                "task %s step %s: invalid answer (call %s)",
                self.task.id,
                self.step.id,
                result.call_id,
            )
        return None

    async def ask_each(self, items: list[Any]) -> list[tuple[Any, dict[str, Any]]]:
        """One question per item, one after another (one GPU). Items without
        a valid answer are skipped; if all of them fail, the step fails."""
        answers = []
        for item in items:
            data = await self.ask(item=item)
            if data is None:
                self.skipped += 1
            else:
                answers.append((item, data))
        if items and not answers:
            raise StepFailed("the model gave no valid answer for any item")
        return answers


Handler = Callable[[StepContext], Awaitable[dict[str, Any]]]
