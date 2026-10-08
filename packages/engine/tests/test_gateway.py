"""The Ollama adapter builds the right request (no real Ollama needed)."""

import json

import httpx

from autolab.db.models.enums import FinishReason
from autolab_engine.budget import Speed
from autolab_engine.gateway.base import GenerateRequest, GenerateResult, Message
from autolab_engine.gateway.ollama import OllamaAdapter


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


async def test_ollama_timeout_and_durations() -> None:
    def ollama(request: httpx.Request) -> httpx.Response:
        # The per-call timeout is used, but never above the adapter's own.
        assert request.extensions["timeout"]["read"] == 30
        return httpx.Response(
            200,
            json={
                "message": {"content": "hi"},
                "prompt_eval_count": 100,
                "prompt_eval_duration": 2_000_000_000,
                "eval_count": 20,
                "eval_duration": 4_000_000_000,
                "done_reason": "stop",
            },
        )

    adapter = OllamaAdapter(30, transport=httpx.MockTransport(ollama))
    result = await adapter.generate(
        GenerateRequest(
            model="m", base_url=None, messages=[Message("user", "Hi")], timeout_seconds=900
        )
    )
    assert (result.prompt_seconds, result.output_seconds) == (2.0, 4.0)


def test_timeout_follows_the_learned_speed() -> None:
    speed = Speed()
    assert speed.timeout(1000, 500) is None  # unknown yet: the adapter's own
    speed.learn(
        GenerateResult(
            text="",
            input_tokens=1000,
            output_tokens=50,
            finish_reason=FinishReason.STOP,
            raw={},
            prompt_seconds=10.0,  # 100 tok/s
            output_seconds=10.0,  # 5 tok/s
        )
    )
    # (1000 / 100 + 900 / 5) x 2 + 120 s to load the model
    assert speed.timeout(1000, 900) == 500.0
    assert speed.timeout(10, 10) == 124.2
