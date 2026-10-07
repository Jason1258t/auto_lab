"""Turn the step outputs into the work (pipeline_spec.md, end of 4).

No model here. The work file gets the title, the summary, a heading and
paragraph per section, and a numbered list of the facts with their exact
quotes and links. In the database: works, work_sources and quotes, in
one transaction.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Quote, Task, Work, WorkSource
from autolab.db.models.enums import SourceKind
from autolab.worker.kinds.base import StepFailed
from autolab.worker.pipelines import PipelineFile


def work_path(settings: Settings, task_id: int, when: datetime) -> Path:
    return Path(settings.data_dir) / "works" / f"{when:%Y}" / f"{when:%m}" / f"{task_id}.md"


def _find(pipeline: PipelineFile, outputs: dict[str, dict[str, Any]], kind: str) -> dict | None:
    """The output of the last step of this kind, if the pipeline has one."""
    for step in reversed(pipeline.steps):
        if step.kind == kind:
            return outputs.get(step.id)
    return None


def render_markdown(
    task: Task, summary: str | None, paragraphs: list[dict], facts: list[dict]
) -> str:
    lines = [f"# {task.title}", ""]
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


async def assemble_work(
    db: AsyncSession,
    settings: Settings,
    task: Task,
    pipeline: PipelineFile,
    outputs: dict[str, dict[str, Any]],
) -> Work:
    written = _find(pipeline, outputs, "write")
    if written is None:
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

    now = datetime.now(UTC)
    path = work_path(settings, task.id, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(task, summary, paragraphs, facts), encoding="utf-8")

    work = await db.get(Work, task.id)
    if work is None:
        work = Work(task_id=task.id, file_path=str(path))
        db.add(work)
    else:  # a revision: replace the evidence
        await db.execute(delete(WorkSource).where(WorkSource.work_id == task.id))
        work.file_path = str(path)
        work.updated_at = now
    work.summary = summary
    await db.flush()

    sources: dict[str, WorkSource] = {}
    for fact in facts:
        url = fact["source"]["url"]
        if url not in sources:
            sources[url] = WorkSource(
                work_id=task.id,
                title=fact["source"]["title"] or url,
                kind=SourceKind.WEB,
                location=url,
                accessed_at=now,
            )
            db.add(sources[url])
    await db.flush()
    db.add_all(
        Quote(
            work_source_id=sources[fact["source"]["url"]].id,
            claim=fact["claim"],
            quote=fact["quote"],
            placement=fact["source"]["url"],
        )
        for fact in facts
    )
    await db.commit()
    return work
