"""Quality set: topics, numbers of a run, reports."""

from pathlib import Path

from autolab_engine.pipelines import load_pipeline
from autolab_engine.quality import (
    Topic,
    compare_markdown,
    load_topics,
    measure,
    report_markdown,
)
from autolab_engine.work import build_work

REPO = Path(__file__).parents[3]


def test_the_topics_file_loads() -> None:
    topics = load_topics(REPO / "quality" / "topics.yaml")
    assert len(topics) == 6
    assert len({t.id for t in topics}) == 6
    assert all("\n" not in t.input for t in topics)


def research_outputs() -> dict:
    source = {"title": "Page", "url": "http://a.test/1"}
    fact = {"claim": "Sky is blue.", "quote": "The sky is blue.", "source": source}
    return {
        "summarize": {"facts": [fact, fact, fact]},
        "verify": {"facts": [fact, fact]},
        "synthesize": {
            "summary": "Short.",
            "sections": [{"heading": "Why", "fact_numbers": [1]}],
            "facts": [fact | {"number": 1}, fact | {"number": 2}],
        },
        "write": {
            "paragraphs": [
                {
                    "heading": "Why",
                    # "No source" is counted in the final text.
                    "text": "Небо голубое из-за 散射 рассеяния [1]. Это красиво. *(⚠ no source)*",
                    "fact_numbers": [1],
                }
            ],
            "unsourced_sentences": 1,
        },
    }


def test_measure_a_research_run() -> None:
    pipeline = load_pipeline(REPO / "pipelines" / "research" / "1.3.0.yaml")
    outputs = research_outputs()
    work = build_work("Небо", pipeline, outputs)
    row = measure(Topic("sky", "Небо", "Почему небо голубое?"), pipeline, outputs, work, 90, 12)
    assert row["minutes"] == 1.5
    assert (row["sections"], row["facts_found"], row["facts_kept"]) == (1, 3, 2)
    assert (row["facts_cited"], row["sources_cited"], row["unsourced_sentences"]) == (1, 1, 1)
    assert row["foreign_letters"] == 2  # 散射
    assert row["language_ok"] is False
    assert row["words"] > 5  # the text without the source list


def test_reports() -> None:
    a = {"title": "v1", "rows": [{"topic": "sky", "words": 100, "minutes": 2.0}]}
    b = {"title": "v2", "rows": [{"topic": "sky", "words": 250, "minutes": 3.5}]}
    assert "| sky | 3.5 (+1.5) | 250 (+150) |" in compare_markdown(a, b)
    text = report_markdown("v2", [*b["rows"], {"topic": "rag", "failed": "no pages"}])
    assert "total (1/2 done)" in text
    assert "- rag: no pages" in text
