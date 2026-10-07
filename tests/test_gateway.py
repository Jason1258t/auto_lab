"""The Ollama adapter builds the right request (no real Ollama needed)."""

import json

import httpx

from autolab.db.models.enums import FinishReason
from autolab.worker.gateway.base import GenerateRequest, Message
from autolab.worker.gateway.ollama import OllamaAdapter


async def test_ollama_request_has_the_context_window() -> None:
    sent: dict = {}

    def ollama(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"ok": true}'},
                "prompt_eval_count": 12,
                "eval_count": 3,
                "done_reason": "length",
            },
        )

    adapter = OllamaAdapter(5, transport=httpx.MockTransport(ollama))
    result = await adapter.generate(
        GenerateRequest(
            model="qwen2.5:3b",
            base_url="http://ollama.test",
            messages=[Message("user", "Hi")],
            schema={"type": "object"},
            params={"temperature": 0, "max_tokens": 50, "context_length": 8192},
        )
    )
    # Without num_ctx Ollama would use its default and cut long prompts.
    assert sent["options"] == {"temperature": 0, "num_predict": 50, "num_ctx": 8192}
    assert sent["format"] == {"type": "object"}
    assert result.finish_reason == FinishReason.LENGTH
    assert (result.input_tokens, result.output_tokens) == (12, 3)
