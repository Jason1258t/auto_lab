"""Text clean-up of deep research 1.3.0: joined marks, JSON paragraphs."""

from autolab_engine.kinds.deep import split_marks, unwrap_json


def test_split_marks() -> None:
    assert split_marks("Blue [3, 5]. Red [7,8].") == "Blue [3][5]. Red [7][8]."


def test_unwrap_json() -> None:
    assert unwrap_json('{"text": "Reranking helps.", "citation": [13]}') == "Reranking helps. [13]"
    assert unwrap_json('{"text": "Reranking helps.", "linking_facts": ["26", "[27]"]}') == (
        "Reranking helps. [26][27]"
    )
    # A mark already in the text is not added again.
    assert (
        unwrap_json('{"text": "Reranking helps [13].", "facts": [13]}') == "Reranking helps [13]."
    )
    assert unwrap_json("Plain text [1].") == "Plain text [1]."
    assert unwrap_json('{"other": 1}') == '{"other": 1}'


def test_is_meta() -> None:
    from autolab_engine.kinds.deep import is_meta

    assert is_meta("Вот введение длиной от 3 до 5 предложений: ...")
    assert is_meta("Here is an introduction of 3 to 5 sentences.")
    assert not is_meta("Квантизация сжимает веса модели.")
    assert not is_meta("Heresy is not a topic here.")


async def test_dedup() -> None:
    import json
    from types import SimpleNamespace

    from autolab_engine.enums import FinishReason
    from autolab_engine.kinds.base import StepContext
    from autolab_engine.kinds.deep import dedup
    from autolab_engine.llm import CallResult
    from autolab_engine.pipelines import Step

    class Llm:
        async def call(self, **_) -> CallResult:
            # 3 = 1 and 4 = 3: a chain, so 3 and 4 go and 1 stays; 9 does not exist.
            data = {
                "repeats": [{"n": 3, "same_as": 1}, {"n": 3, "same_as": 4}, {"n": 9, "same_as": 1}]
            }
            return CallResult(1, json.dumps(data), data, FinishReason.STOP)

    facts = [
        {"number": 1, "claim": "MVCC keeps row versions."},
        {"number": 2, "claim": "mvcc keeps row versions"},  # an exact repeat of 1
        {"number": 3, "claim": "PostgreSQL stores several versions of a row."},
        {"number": 4, "claim": "Old row versions stay in the table."},
        {"number": 5, "claim": "VACUUM removes dead rows."},
    ]
    sections = [
        {"heading": "MVCC", "question": "?", "fact_numbers": [1, 2, 3, 4, 5], "facts": facts},
        {
            "heading": "One",
            "question": "?",
            "fact_numbers": [6],
            "facts": [{"number": 6, "claim": "x"}],
        },
    ]
    output = {"type": "object", "required": ["repeats"]}
    step = Step.model_validate(
        {"id": "dedup", "kind": "dedup", "for_each": "group.sections",
         "llm": {"prompt": "{{ item.heading }}", "output": output}}
    )  # fmt: skip
    task = SimpleNamespace(id=1, model_id=1, title="T", input="T")
    ctx = StepContext(task, None, step, 1, {"group": {"sections": sections}}, Llm())
    result = await dedup(ctx)
    assert [f["number"] for f in result["sections"][0]["facts"]] == [1, 5]
    assert result["sections"][0]["fact_numbers"] == [1, 5]
    assert result["sections"][1]["fact_numbers"] == [6]  # one fact: not asked
    assert result["dropped"] == 3
