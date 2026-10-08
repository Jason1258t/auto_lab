"""How a step asks a model: the LlmClient interface.

The engine does not decide how calls are queued or recorded. AutoLab's
worker implements LlmClient with its LLM manager (one queue per model,
llm_calls rows, a log store); the command line calls the gateway
directly.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

import jsonschema

from autolab_engine.enums import FinishReason
from autolab_engine.gateway import Message


class LlmCallFailed(Exception):
    """The provider could not answer. The message is safe for users."""


class PromptTooLong(LlmCallFailed):
    """The prompt leaves no room for an answer in the model's window.
    Trying again with the same prompt cannot help."""


@dataclass(frozen=True)
class CallResult:
    call_id: int | None  # the caller's id of this call, for logs
    text: str
    # The parsed answer if a schema was given and the answer matches it;
    # None otherwise (the caller may try again).
    data: dict[str, Any] | None
    finish_reason: FinishReason


class LlmClient(Protocol):
    """One model call for the current task. Raises LlmCallFailed (or
    PromptTooLong) when there is no answer."""

    async def call(
        self,
        *,
        step_index: int,
        messages: list[Message],
        schema: dict[str, Any] | None,
        params: dict[str, Any],
        attempt: int,
    ) -> CallResult: ...


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
