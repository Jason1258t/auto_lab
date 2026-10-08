"""The model gateway interface (ARCHITECTURE.md, "Model gateway").

Pipeline code never talks to a provider directly. It sends a
GenerateRequest; the adapter of the model's provider answers.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from autolab.db.models.enums import FinishReason


@dataclass(frozen=True)
class Message:
    role: str  # "system" or "user"
    content: str


@dataclass(frozen=True)
class GenerateRequest:
    model: str  # the name the provider API expects, e.g. "llama3.1:8b"
    base_url: str | None
    messages: list[Message]
    schema: dict[str, Any] | None = None  # JSON schema for structured output
    params: dict[str, Any] = field(default_factory=dict)  # temperature, max_tokens
    # Per-call timeout from the token budget; None = the adapter's own
    # (which is also the upper bound).
    timeout_seconds: float | None = None

    def as_log(self) -> dict[str, Any]:
        """What goes into the log store."""
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
            "schema": self.schema,
            "params": self.params,
        }


@dataclass(frozen=True)
class GenerateResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: FinishReason
    raw: dict[str, Any]  # the provider's full answer, for the log store
    # Time spent reading the prompt and writing the answer, if the
    # provider tells it. The manager learns the model's speed from it.
    prompt_seconds: float | None = None
    output_seconds: float | None = None


class GatewayError(Exception):
    """The provider could not answer (down, timeout, bad model name)."""


class Adapter(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...
