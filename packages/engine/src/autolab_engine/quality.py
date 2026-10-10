"""The quality set: run a pipeline version on fixed topics and measure.

No model here: every number comes from the step outputs and the work.
The numbers do not judge the text by themselves (read the works!), but
they make two versions comparable: how much text, how many cited facts
and sources, sentences without a source, wrong letters, time.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from autolab_engine.language import detect, foreign_letters, matches
from autolab_engine.pipelines import PipelineFile
from autolab_engine.work import WorkResult

SOURCES_HEADING = "\n## Sources\n"
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    input: str


def load_topics(path: Path) -> list[Topic]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Topic(t["id"], t["title"], " ".join(t["input"].split())) for t in data["topics"]]


def _of_kind(pipeline: PipelineFile, outputs: dict[str, dict], kind: str) -> list[dict]:
    return [outputs[s.id] for s in pipeline.steps if s.kind == kind and s.id in outputs]


def measure(
    topic: Topic,
    pipeline: PipelineFile,
    outputs: dict[str, dict[str, Any]],
    work: WorkResult | None,
    seconds: float,
    calls: int,
) -> dict[str, Any]:
    """Numbers of one finished run."""
    text = work.markdown if work else ""
    body = text.split(SOURCES_HEADING)[0]  # the text without the source list
    language = detect(f"{topic.title}\n{topic.input}")
    written = [
        o for kind in ("write", "write_parts", "cover") for o in _of_kind(pipeline, outputs, kind)
    ]
    # A section: a paragraph of `write`, or a part of `write_parts` /
    # `cover` (1.3.0+; cover comes last, with the final texts).
    paragraphs = (written[-1].get("paragraphs") or written[-1].get("parts")) if written else []
    facts_found = sum(len(o.get("facts", [])) for o in _of_kind(pipeline, outputs, "summarize"))
    verified = _of_kind(pipeline, outputs, "verify")
    found = {
        "topic": topic.id,
        "minutes": round(seconds / 60, 1),
        "calls": calls,
        "words": len(_WORD.findall(body)),
        "sections": len(paragraphs),
        "words_per_section": round(len(_WORD.findall(body)) / len(paragraphs)) if paragraphs else 0,
        "facts_found": facts_found,
        "facts_kept": len(verified[-1]["facts"]) if verified else None,
        "facts_cited": len(work.facts) if work else 0,
        "sources_cited": len({f["source"]["url"] for f in work.facts}) if work else 0,
        "unsourced_sentences": sum(o.get("unsourced_sentences", 0) for o in written),
        "foreign_letters": len(foreign_letters(body, language)),
        "language_ok": bool(body) and matches(body, language),
    }
    # Deep research: how many sub-questions got a section.
    for step in pipeline.steps:
        if step.kind == "group" and step.id in outputs:
            ref = step.config.get("questions_from", "")
            step_id, _, field = ref.partition(".")
            asked = len(outputs.get(step_id, {}).get(field, []))
            found["questions_covered"] = f"{len(outputs[step.id]['sections'])}/{asked}"
    return found


COLUMNS = [
    ("topic", "Topic"),
    ("minutes", "Min"),
    ("calls", "Calls"),
    ("words", "Words"),
    ("sections", "Sections"),
    ("words_per_section", "Words/sect."),
    ("facts_found", "Facts found"),
    ("facts_kept", "Kept"),
    ("facts_cited", "Cited"),
    ("sources_cited", "Sources"),
    ("unsourced_sentences", "No source"),
    ("foreign_letters", "Wrong letters"),
    ("questions_covered", "Questions"),
]


def _table(rows: list[dict[str, Any]]) -> list[str]:
    columns = [(k, h) for k, h in COLUMNS if any(k in r for r in rows)]
    lines = ["| " + " | ".join(h for _, h in columns) + " |"]
    lines.append("|" + "---|" * len(columns))
    for row in rows:
        lines.append("| " + " | ".join(_cell(row.get(k)) for k, _ in columns) + " |")
    return lines


def _cell(value: Any) -> str:
    return "—" if value is None else str(value)


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sums over the finished topics (minutes, words, facts...)."""
    done = [r for r in rows if not r.get("failed")]
    keys = ["minutes", "calls", "words", "facts_found", "facts_cited", "sources_cited"]
    keys += ["unsourced_sentences", "foreign_letters"]
    found: dict[str, Any] = {"topic": f"total ({len(done)}/{len(rows)} done)"}
    for key in keys:
        found[key] = round(sum(r.get(key) or 0 for r in done), 1)
    return found


def report_markdown(title: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", ""]
    lines += _table([*rows, totals(rows)])
    failed = [r for r in rows if r.get("failed")]
    if failed:
        lines += ["", "Failed:", ""] + [f"- {r['topic']}: {r['failed']}" for r in failed]
    return "\n".join(lines) + "\n"


def compare_markdown(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Two eval reports side by side: per topic, B's numbers with the
    change from A."""
    lines = [f"# {a['title']} → {b['title']}", ""]
    old = {r["topic"]: r for r in a["rows"]}
    rows = []
    for row in b["rows"]:
        before = old.get(row["topic"], {})
        rows.append({k: _delta(v, before.get(k)) for k, v in row.items()})
    lines += _table(rows)
    return "\n".join(lines) + "\n"


def _delta(new: Any, old: Any) -> Any:
    if isinstance(new, int | float) and not isinstance(new, bool) and isinstance(old, int | float):
        change = round(new - old, 1)
        return f"{new} ({'+' if change >= 0 else ''}{change})"
    return new
