"""Build the work (the final Markdown text) from the step outputs.

No model and no database here. A text work gets the title, the summary,
a heading and paragraph per section, and a numbered list of the cited
facts with their exact quotes and links. A code work gets the checked
files. AutoLab's worker saves the result and its evidence rows.
"""

from dataclasses import dataclass, field
from typing import Any

from autolab_engine.kinds.base import StepFailed
from autolab_engine.pipelines import PipelineFile


@dataclass
class WorkResult:
    summary: str | None
    markdown: str
    # Facts the text cites: number, claim, quote, source {title, url}.
    facts: list[dict] = field(default_factory=list)


def _find(pipeline: PipelineFile, outputs: dict[str, dict[str, Any]], kind: str) -> dict | None:
    """The output of the last step of this kind, if the pipeline has one."""
    for step in reversed(pipeline.steps):
        if step.kind == kind:
            return outputs.get(step.id)
    return None


def render_markdown(
    title: str, summary: str | None, paragraphs: list[dict], facts: list[dict]
) -> str:
    lines = [f"# {title}", ""]
    if summary:
        lines += [summary, ""]
    for paragraph in paragraphs:
        lines += [f"## {paragraph['heading']}", "", paragraph["text"], ""]
    if facts:
        lines += ["## Sources", ""]
        for fact in facts:
            source = fact["source"]
            link = f"[{source['title'] or source['url']}]({source['url']})"
            lines += [
                f'**[{fact["number"]}]** {fact["claim"]} \u2014 "{fact["quote"]}" ({link})',
                "",
            ]
    return "\n".join(lines)


# Code fences by file extension (only for display).
_FENCE_LANG = {
    "py": "python", "js": "javascript", "ts": "typescript", "sh": "bash", "toml": "toml",
    "json": "json", "md": "markdown", "yaml": "yaml", "yml": "yaml", "txt": "",
}  # fmt: skip


def _first_value(outputs: dict[str, dict[str, Any]], key: str) -> Any:
    """The value of `key` in the first step output that has it."""
    for output in outputs.values():
        if output.get(key):
            return output[key]
    return None


def render_code(
    title: str, pipeline: PipelineFile, outputs: dict[str, dict[str, Any]]
) -> tuple[str | None, str]:
    """(summary, markdown) of a code work: the files of the last check
    step, their remaining problems, review issues and usage notes."""
    checked = _find(pipeline, outputs, "code_check")
    summary = _first_value(outputs, "summary")
    lines = [f"# {title}", ""]
    if summary:
        lines += [summary, ""]
    lines += [
        "*Checked by static analysis only (syntax, ruff). The code was never run.*",
        "",
        "## Files",
        "",
    ]
    for f in checked["files"]:
        lang = _FENCE_LANG.get(f["path"].rpartition(".")[2], "")
        lines += [f"### `{f['path']}`", ""]
        if f.get("purpose"):
            lines += [f["purpose"], ""]
        lines += [f"```{lang}", f["code"].rstrip(), "```", ""]
    lines += ["## Static checks", ""]
    if checked["problems"]:
        for f in checked["files"]:
            lines += [f"- `{f['path']}`: {p}" for p in f["problems"]]
    else:
        lines.append("No problems found.")
    lines.append("")
    issues = (_find(pipeline, outputs, "code_review") or {}).get("issues") or []
    if issues:
        lines += ["## Review notes from the model", ""]
        lines += [f"- `{i['path']}`: {i['issue']}" for i in issues]
        lines.append("")
    usage = _first_value(outputs, "usage")
    if usage:
        lines += ["## How to use", "", usage, ""]
    return summary, "\n".join(lines)


def build_work(
    title: str, pipeline: PipelineFile, outputs: dict[str, dict[str, Any]]
) -> WorkResult:
    """The work of a finished run. Raises StepFailed if the outputs give
    no text, or no cited fact where the pipeline requires evidence."""
    written = _find(pipeline, outputs, "write")
    if written is None:
        if _find(pipeline, outputs, "code_check") is not None:
            return WorkResult(*render_code(title, pipeline, outputs))
        raise StepFailed("the pipeline has no write step, so there is no text")
    # The report plan: synthesize (research) or group (deep research).
    plan = _find(pipeline, outputs, "synthesize") or _find(pipeline, outputs, "group") or {}
    paragraphs = written["paragraphs"]
    # A summary written after the text (deep research) wins over the plan's.
    summary = (_find(pipeline, outputs, "abstract") or {}).get("summary") or plan.get("summary")

    # Only facts that the text really cites become evidence.
    cited = {n for p in paragraphs for n in p["fact_numbers"]}
    facts = [f for f in plan.get("facts", []) if f["number"] in cited]
    if pipeline.evidence == "required" and not facts:
        raise StepFailed("the text cites no fact, but this pipeline requires sources")
    return WorkResult(summary, render_markdown(title, summary, paragraphs, facts), facts)


def has_work(pipeline: PipelineFile) -> bool:
    """A work comes from a write step (text) or a code_check step (code)."""
    return any(step.kind in ("write", "code_check") for step in pipeline.steps)
