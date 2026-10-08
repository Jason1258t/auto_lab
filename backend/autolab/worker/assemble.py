"""Save the work of a finished task (pipeline_spec.md, end of 4).

The text itself is built by the engine (autolab_engine.work). Here: the
file under data/works, and works, work_sources and quotes in the
database, in one transaction.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Quote, Task, Work, WorkSource
from autolab.db.models.enums import SourceKind
from autolab_engine.pipelines import PipelineFile
from autolab_engine.work import build_work


def work_path(settings: Settings, task_id: int, when: datetime) -> Path:
    return Path(settings.data_dir) / "works" / f"{when:%Y}" / f"{when:%m}" / f"{task_id}.md"


async def assemble_work(
    db: AsyncSession,
    settings: Settings,
    task: Task,
    pipeline: PipelineFile,
    outputs: dict[str, dict[str, Any]],
) -> Work:
    result = build_work(task.title, pipeline, outputs)
    now = datetime.now(UTC)
    path = work_path(settings, task.id, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.markdown, encoding="utf-8")

    work = await db.get(Work, task.id)
    if work is None:
        work = Work(task_id=task.id, file_path=str(path))
        db.add(work)
    else:  # a revision: replace the evidence
        await db.execute(delete(WorkSource).where(WorkSource.work_id == task.id))
        work.file_path = str(path)
        work.updated_at = now
    work.summary = result.summary
    await db.flush()

    sources: dict[str, WorkSource] = {}
    for fact in result.facts:
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
        for fact in result.facts
    )
    await db.commit()
    return work
