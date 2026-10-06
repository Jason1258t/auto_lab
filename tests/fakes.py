"""Test doubles for the worker: a model that answers from a function."""

from collections.abc import Callable

from autolab.db.models.enums import FinishReason
from autolab.worker.gateway import GenerateRequest, GenerateResult


class FakeAdapter:
    """answer(request) returns the model text, or raises GatewayError."""

    def __init__(self, answer: Callable[[GenerateRequest], str]) -> None:
        self.answer = answer
        self.requests: list[GenerateRequest] = []

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        self.requests.append(request)
        return GenerateResult(
            text=self.answer(request),
            input_tokens=12,
            output_tokens=5,
            finish_reason=FinishReason.STOP,
            raw={"fake": True},
        )
