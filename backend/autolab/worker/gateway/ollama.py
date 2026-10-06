"""Ollama adapter: POST /api/chat with structured output."""

import httpx

from autolab.db.models.enums import FinishReason
from autolab.worker.gateway.base import GatewayError, GenerateRequest, GenerateResult

DEFAULT_BASE_URL = "http://localhost:11434"

# Ollama's done_reason -> our finish_reason. Anything else -> other.
FINISH_REASONS = {"stop": FinishReason.STOP, "length": FinishReason.LENGTH}


class OllamaAdapter:
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        options = {}
        if "temperature" in request.params:
            options["temperature"] = request.params["temperature"]
        if "max_tokens" in request.params:
            options["num_predict"] = request.params["max_tokens"]
        body = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": options,
        }
        if request.schema is not None:
            body["format"] = request.schema  # Ollama structured outputs

        url = (request.base_url or DEFAULT_BASE_URL).rstrip("/") + "/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
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
        )
