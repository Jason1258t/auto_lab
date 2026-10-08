"""Ollama adapter: POST /api/chat with structured output."""

import httpx

from autolab_engine.enums import FinishReason
from autolab_engine.gateway.base import GatewayError, GenerateRequest, GenerateResult

DEFAULT_BASE_URL = "http://localhost:11434"

# Ollama's done_reason -> our finish_reason. Anything else -> other.
FINISH_REASONS = {"stop": FinishReason.STOP, "length": FinishReason.LENGTH}


def seconds(nanoseconds: int | None) -> float | None:
    return nanoseconds / 1e9 if nanoseconds else None


class OllamaAdapter:
    def __init__(
        self, timeout_seconds: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.timeout_seconds = timeout_seconds  # the upper bound for every call
        self.transport = transport  # tests only

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        options = {}
        if "temperature" in request.params:
            options["temperature"] = request.params["temperature"]
        if "max_tokens" in request.params:
            options["num_predict"] = request.params["max_tokens"]
        if "context_length" in request.params:
            options["num_ctx"] = request.params["context_length"]
        body = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": options,
        }
        if request.schema is not None:
            body["format"] = request.schema  # Ollama structured outputs

        url = (request.base_url or DEFAULT_BASE_URL).rstrip("/") + "/api/chat"
        timeout = min(request.timeout_seconds or self.timeout_seconds, self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=10.0), transport=self.transport
            ) as client:
                response = await client.post(url, json=body)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GatewayError(f"Ollama call failed: {exc}") from exc

        return GenerateResult(
            text=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            finish_reason=FINISH_REASONS.get(data.get("done_reason"), FinishReason.OTHER),
            raw=data,
            prompt_seconds=seconds(data.get("prompt_eval_duration")),
            output_seconds=seconds(data.get("eval_duration")),
        )
