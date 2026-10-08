"""Several items per model call (config.batch_size, token_budgets.md phase 3)."""

import json
from types import SimpleNamespace

import pytest

from autolab.db.models.enums import FinishReason
from autolab.worker.kinds.base import StepContext, StepFailed
from autolab.worker.llm_manager import CallResult
from autolab.worker.pipelines import Step

OUTPUT = {
    "type": "object",
    "required": ["answers"],
    "properties": {
        "answers": {
            "type": "array",
            "items": {"type": "object", "required": ["n", "ok"]},
        }
    },
}


class FakeLlm:
    """answer(items) -> the list of answers the model gives."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.batches: list[list[str]] = []

    async def call(self, *, messages, **_) -> CallResult:
        items = json.loads(messages[-1].content.split("\n")[0])
        self.batches.append(items)
        data = {"answers": self.answer(items)}
        return CallResult(1, json.dumps(data), data, FinishReason.STOP)


def context(llm: FakeLlm, batch_size: int) -> StepContext:
    step = Step.model_validate(
        {
            "id": "verify",
            "kind": "verify",
            "config": {"batch_size": batch_size},
            "llm": {"prompt": "{{ items | tojson }}", "output": OUTPUT},
        }
    )
    task = SimpleNamespace(id=1, model_id=1, title="Sky", input="Why is the sky blue?")
    return StepContext(task, None, step, 0, {}, llm, None)


async def test_batches_and_a_left_out_item_asked_alone() -> None:
    def answer(items: list[str]) -> list[dict]:
        # The model forgets "c" in a full batch, and gives a wrong n.
        found = [
            {"n": i, "ok": True} for i, x in enumerate(items, 1) if x != "c" or len(items) == 1
        ]
        return found + [{"n": 9, "ok": False}]

    llm = FakeLlm(answer)
    ctx = context(llm, 3)
    answers = await ctx.ask_each(["a", "b", "c", "d", "e"])

    assert llm.batches == [["a", "b", "c"], ["d", "e"], ["c"]]
    assert [item for item, _ in answers] == ["a", "b", "c", "d", "e"]  # in order
    assert answers[0][1] == {"ok": True}  # n is removed
    assert ctx.skipped == 0


async def test_items_without_answers_are_skipped() -> None:
    llm = FakeLlm(lambda items: [{"n": 1, "ok": True}] if items[0] == "a" else [])
    ctx = context(llm, 2)
    answers = await ctx.ask_each(["a", "b", "c"])
    assert [item for item, _ in answers] == ["a"]
    assert ctx.skipped == 2

    with pytest.raises(StepFailed, match="no valid answer"):
        await context(FakeLlm(lambda items: []), 2).ask_each(["x"])
