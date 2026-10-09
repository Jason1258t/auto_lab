"""The search step: one more round for empty queries (config.min_candidates)."""

from types import SimpleNamespace

import httpx
import pytest

from autolab_engine.kinds import research
from autolab_engine.kinds.base import StepContext
from autolab_engine.pipelines import Step


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(research, "SEARCH_RETRY_SECONDS", (0.0, 0.0))
    monkeypatch.setattr(research, "SEARCH_ROUND_PAUSE", 0.0)


def context(config: dict, blocked_calls: int) -> tuple[StepContext, list[str]]:
    """Query "b" finds nothing for the first `blocked_calls` requests."""
    asked: list[str] = []

    def web(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        asked.append(query)
        if query == "b" and asked.count("b") <= blocked_calls:
            return httpx.Response(200, json={"results": []})
        urls = [f"http://{query}{n}.test/" for n in range(3)]
        return httpx.Response(
            200, json={"results": [{"title": u, "url": u, "content": ""} for u in urls]}
        )

    step = Step.model_validate(
        {"id": "s", "kind": "search", "from": "plan.queries", "config": config}
    )
    task = SimpleNamespace(id=1, model_id=1, title="T", input="T")
    ctx = StepContext(
        task,
        None,
        step,
        1,
        {"plan": {"queries": ["a", "b"]}},
        llm=None,
        searxng_url="http://searx.test",
        http=httpx.AsyncClient(transport=httpx.MockTransport(web)),
    )
    return ctx, asked


async def test_empty_queries_get_one_more_round() -> None:
    config = {"results_per_query": 3, "max_candidates": 10, "min_candidates": 5}
    ctx, asked = context(config, blocked_calls=3)  # 3 = the first try and two retries
    output = await research.search(ctx)
    assert len(output["results"]) == 6
    assert asked == ["a", "b", "b", "b", "b"]
    assert ctx.notes == ["1 empty queries tried again"]


async def test_no_more_round_when_enough_candidates() -> None:
    config = {"results_per_query": 3, "max_candidates": 10, "min_candidates": 3}
    ctx, asked = context(config, blocked_calls=3)
    output = await research.search(ctx)
    assert len(output["results"]) == 3
    assert asked == ["a", "b", "b", "b"]
    assert ctx.notes == []
