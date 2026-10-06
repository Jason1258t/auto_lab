"""Reading results: the work (text, sources, quotes) and the LLM calls.

Who sees a work: members always; in a public workspace anyone, but only
works of accepted (done) tasks. LLM calls and logs: members only.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import LlmCall, LlmResponse, Quote, Task, User, Work, WorkSource
from autolab.db.models.enums import TaskStatus
from autolab.errors import AppError
from autolab.logstore import LogStore
from autolab.services.permissions import WorkspaceAccess, load_access, require_inside
from autolab.services.tasks import load_task


@dataclass(frozen=True)
class SourceView:
    source: WorkSource
    quotes: list[Quote]


@dataclass(frozen=True)
class WorkView:
    task: Task
    work: Work
    text: str
    sources: list[SourceView]


def work_not_found(task_id: int) -> AppError:
    return AppError(404, "work_not_found", f"Task {task_id} has no work to show")


def _public_ok(access: WorkspaceAccess, task: Task) -> bool:
    return access.can_see_inside or task.status == TaskStatus.DONE


async def get_work(db: AsyncSession, task_id: int, user: User | None) -> WorkView:
    task = await db.get(Task, task_id)
    if task is None:
        raise work_not_found(task_id)
    try:
        access = await load_access(db, task.workspace_id, user)
    except AppError:
        raise work_not_found(task_id) from None
    work = await db.get(Work, task_id)
    if work is None or not _public_ok(access, task):
        raise work_not_found(task_id)

    sources = list(
        await db.scalars(
            select(WorkSource).where(WorkSource.work_id == task_id).order_by(WorkSource.id)
        )
    )
    quotes = list(
        await db.scalars(
            select(Quote)
            .where(Quote.work_source_id.in_([s.id for s in sources]))
            .order_by(Quote.id)
        )
    )
    path = Path(work.file_path)
    text = await asyncio.to_thread(path.read_text, encoding="utf-8") if path.exists() else ""
    return WorkView(
        task=task,
        work=work,
        text=text,
        sources=[SourceView(s, [q for q in quotes if q.work_source_id == s.id]) for s in sources],
    )


async def list_works(
    db: AsyncSession, access: WorkspaceAccess, limit: int, offset: int
) -> list[tuple[Task, Work]]:
    """Works of a workspace, newest first. Outsiders of a public workspace
    see only accepted ones."""
    query = (
        select(Task, Work)
        .join(Work, Work.task_id == Task.id)
        .where(Task.workspace_id == access.workspace.id)
        .order_by(Work.updated_at.desc(), Task.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if not access.can_see_inside:
        query = query.where(Task.status == TaskStatus.DONE)
    return [(task, work) for task, work in await db.execute(query)]


async def list_calls(
    db: AsyncSession, task_id: int, user: User
) -> list[tuple[LlmCall, LlmResponse | None]]:
    view, access = await load_task(db, task_id, user)
    require_inside(access)
    rows = await db.execute(
        select(LlmCall, LlmResponse)
        .outerjoin(LlmResponse, LlmResponse.call_id == LlmCall.id)
        .where(LlmCall.task_id == task_id)
        .order_by(LlmCall.id)
    )
    return [(call, response) for call, response in rows]


async def get_call_log(db: AsyncSession, log_store: LogStore, call_id: int, user: User) -> dict:
    """The full prompt and answer of one call, from the log store."""
    call = await db.get(LlmCall, call_id)
    if call is None:
        raise AppError(404, "call_not_found", f"Call {call_id} not found")
    try:
        await load_task(db, call.task_id, user)
    except AppError:
        raise AppError(404, "call_not_found", f"Call {call_id} not found") from None
    log = await log_store.get(call_id)
    if log is None:
        raise AppError(404, "log_not_found", f"No log for call {call_id}")
    return log
