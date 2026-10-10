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


async def test_cover() -> None:
    import json
    from types import SimpleNamespace

    from autolab_engine.enums import FinishReason
    from autolab_engine.kinds.base import StepContext
    from autolab_engine.kinds.deep import cover
    from autolab_engine.llm import CallResult
    from autolab_engine.pipelines import Step

    class Llm:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def call(self, *, messages, **_) -> CallResult:
            prompt = messages[-1].content
            self.prompts.append(prompt)
            if "Part: B" in prompt:  # B: uses the facts it is given
                data = {"paragraph": "Dead rows stay until VACUUM [3]. It frees space [4]."}
            else:  # A: writes without the new fact (and a wrong mark)
                data = {"paragraph": "MVCC is useful for many reasons [9]."}
            return CallResult(1, json.dumps(data), data, FinishReason.STOP)

    plan = [
        {"section": "S", "heading": "A", "point": "p", "facts": [
            {"number": 1, "claim": "c1"}, {"number": 2, "claim": "c2"}]},
        {"section": "S", "heading": "B", "point": "p", "facts": [{"number": 3, "claim": "c3"}]},
    ]  # fmt: skip
    written = [{"section": "S", "heading": "A", "text": "MVCC keeps versions [1].",
                "fact_numbers": [1]}]  # B was not written  # fmt: skip
    sections = [{"heading": "S", "facts": [{"number": n, "claim": f"c{n}"} for n in (1, 2, 3, 4)]}]
    config = {"plan": "subplan.parts", "parts": "write.parts", "sections": "dedup.sections"}
    step = Step.model_validate(
        {"id": "cover", "kind": "cover", "config": config,
         "llm": {"prompt": "Part: {{ item.heading }} {{ item.facts | tojson }}",
                 "output": {"type": "object"}}}
    )  # fmt: skip
    outputs = {
        "subplan": {"parts": plan},
        "write": {"parts": written},
        "dedup": {"sections": sections},
    }
    task = SimpleNamespace(id=1, model_id=1, title="T", input="T")
    llm = Llm()
    ctx = StepContext(task, None, step, 1, outputs, llm)
    result = await cover(ctx)
    # A: fact 2 asked once; the answer cites no new fact, so A is not asked again.
    # B: not written before; it gets fact 3 and fact 4 (left out by subplan).
    assert [p["heading"] for p in result["parts"]] == ["A", "B"]
    assert result["parts"][0]["text"] == "MVCC keeps versions [1]."
    assert result["parts"][1]["text"] == "Dead rows stay until VACUUM [3]. It frees space [4]."
    assert result["coverage"][0] == {
        "section": "S", "heading": "A", "planned": [1, 2], "used": [1], "unused": [2]
    }  # fmt: skip
    assert result["unused"] == 1 and result["added_paragraphs"] == 1
    assert len(llm.prompts) == 2


async def test_check_text() -> None:
    import json
    from types import SimpleNamespace

    from autolab_engine.enums import FinishReason
    from autolab_engine.kinds.base import StepContext
    from autolab_engine.kinds.deep import check_text
    from autolab_engine.kinds.research import NO_SOURCE
    from autolab_engine.llm import CallResult
    from autolab_engine.pipelines import Step

    seen: list[dict] = []

    class Llm:
        async def call(self, *, messages, **_) -> CallResult:
            items = json.loads(messages[-1].content)
            seen.extend(items)
            verdicts = {"lock": "wrong", "fast": "new"}
            answers = [
                {"n": i, "verdict": next((v for k, v in verdicts.items() if k in s["text"]), "ok")}
                for i, s in enumerate(items, 1)
            ]
            data = {"answers": answers}
            return CallResult(1, json.dumps(data), data, FinishReason.STOP)

    facts = [
        {"number": 1, "claim": "c", "quote": "Old row versions stay."},
        {"number": 2, "claim": "c", "quote": "VACUUM removes dead rows."},
    ]
    text = (
        f"Old versions stay [1]. A transaction holds a lock on the row. {NO_SOURCE} "
        f"So it waits. {NO_SOURCE}\n\n"
        "VACUUM removes them [2]. It is very fast [2]."
    )
    parts = [{"section": "S", "heading": "A", "text": text, "fact_numbers": [1, 2]}]
    step = Step.model_validate(
        {"id": "check", "kind": "check_text",
         "config": {"parts": "cover.parts", "facts": "group.facts", "batch_size": 4},
         "llm": {"prompt": "{{ items | tojson }}",
                 "output": {"type": "object", "required": ["answers"], "properties": {
                     "answers": {"type": "array", "items": {"required": ["n"]}}}}}}
    )  # fmt: skip
    task = SimpleNamespace(id=1, model_id=1, title="T", input="T")
    outputs = {"cover": {"parts": parts}, "group": {"facts": facts}}
    result = await check_text(StepContext(task, None, step, 1, outputs, Llm()))
    # The sentence without a mark is checked against its paragraph's quote.
    lock = next(s for s in seen if "lock" in s["text"])
    assert lock["text"] == "A transaction holds a lock on the row."
    assert lock["quotes"] == ["Old row versions stay."]
    assert result["parts"][0]["text"] == (
        f"Old versions stay [1]. So it waits. {NO_SOURCE}\n\nVACUUM removes them [2]."
    )
    assert [r["verdict"] for r in result["removed"]] == ["wrong", "new"]
    assert result["unsourced_sentences"] == 1
