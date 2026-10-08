"""What a step kind gets to do its work (drafts/pipeline_spec.md, 4-6)."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from autolab.config import Settings
from autolab.db.models import Model, Task
from autolab.db.models.enums import FinishReason
from autolab.worker import templates
from autolab.worker.gateway import Message
from autolab.worker.language import Language, detect, matches
from autolab.worker.language import note as language_note
from autolab.worker.llm_manager import LlmCallFailed, LlmManager, PromptTooLong
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
    # Short notes the runner adds to the step summary, e.g. "2 sentences
    # without a source" (pipeline files cannot change after sync).
    notes: list[str] = field(default_factory=list)
    wrong_language: int = field(default=0)  # texts still not in the task language
    model: Model | None = None  # the task's model (size class, window)

    @property
    def language(self) -> Language:
        """The language of the task (by its alphabet); the model writes in it."""
        return detect(f"{self.task.title}\n{self.task.input}")

    def resolve(self, ref: str | list[str]) -> Any:
        """'<step id>.<field>' -> that field of the earlier step's output.
        A list of references -> their lists joined into one."""
        if isinstance(ref, list):
            joined: list[Any] = []
            for one in ref:
                joined += self.resolve(one)
            return joined
        step_id, _, name = ref.partition(".")
        try:
            return self.outputs[step_id][name]
        except KeyError as exc:
            raise StepFailed(f"no '{ref}' in the output of step '{step_id}'") from exc

    def variables(self, **extra: Any) -> dict[str, Any]:
        found = {
            "task": {
                "title": self.task.title,
                "input": self.task.input,
                "language": self.language.name,
            },
            "config": self.step.config,
            # Outputs of earlier steps, e.g. {{ steps.outline.questions }}.
            "steps": self.outputs,
        }
        if self.step.from_:
            found["input"] = self.resolve(self.step.from_)
        return found | extra

    def messages(self, variables: dict[str, Any], extra_note: str | None = None) -> list[Message]:
        llm = self.step.llm
        prompt = templates.render(llm.prompt, variables)
        # Added by code, so every pipeline version gets them: the revise
        # note, the language of the task, and a one-off note (a retry).
        for line in (self.note, language_note(self.language), extra_note):
            if line:
                prompt += "\n\n" + line
        found = [Message("system", templates.render(llm.system, variables))] if llm.system else []
        return found + [Message("user", prompt)]

    async def ask(self, *, extra_note: str | None = None, **extra: Any) -> dict[str, Any] | None:
        """One model answer that matches the output schema, trying up to
        max_attempts times. None if no attempt gave a valid answer."""
        llm = self.step.llm
        messages = self.messages(self.variables(**extra), extra_note)
        max_tokens = llm.max_tokens
        for attempt in range(1, llm.max_attempts + 1):
            try:
                result = await self.llm.call(
                    task_id=self.task.id,
                    step_index=self.step_index,
                    model_id=self.task.model_id,
                    messages=messages,
                    schema=llm.output,
                    params={"temperature": llm.temperature, "max_tokens": max_tokens},
                    attempt=attempt,
                )
            except PromptTooLong as exc:  # a retry cannot help
                raise StepFailed(str(exc)[0].lower() + str(exc)[1:]) from exc
            except LlmCallFailed:
                continue
            if result.data is not None:
                return result.data
            # Cut by the limit: the same limit would cut it again. The
            # manager lowers it back if the window is too small.
            if result.finish_reason == FinishReason.LENGTH:
                max_tokens *= 2
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

    async def in_task_language(self, item: Any, answer: dict[str, Any], key: str) -> dict[str, Any]:
        """If answer[key] is not in the task language, ask once more with a
        clear note. Returns the better answer; a still wrong one is counted
        in the step summary."""
        language = self.language
        if matches(answer[key], language):
            return answer
        retry = await self.ask(
            item=item,
            extra_note=f"Your last answer was not in {language.name}. Write it in {language.name}.",
        )
        if retry is not None and matches(retry[key], language):
            return retry
        self.wrong_language += 1
        return answer


Handler = Callable[[StepContext], Awaitable[dict[str, Any]]]
