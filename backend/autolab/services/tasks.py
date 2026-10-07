"""Tasks: create, list, edit, queue, cancel, delete.

No worker yet: `queue` only sets the status. Status changes allowed
here:
    draft -> queued (queue)
    queued / running / in_review -> cancelled (cancel)
The worker and reviews move a task further (later steps).
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import (
    Membership,
    Model,
    Pipeline,
    PipelineVersion,
    Task,
    TaskStep,
    User,
)
from autolab.db.models.enums import TaskStatus
from autolab.errors import AppError
from autolab.services import activity
from autolab.services.permissions import (
    WorkspaceAccess,
    load_access,
    require_inside,
    require_not_archived,
    require_task_editor,
)
from autolab.worker.pipelines import PipelineError, load_pipeline
from autolab.worker.runner import rerun_start

log = logging.getLogger(__name__)

CANCELLABLE = {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.IN_REVIEW}


@dataclass(frozen=True)
class TaskView:
    """A task with the names a client needs to show it."""

    task: Task
    pipeline_name: str
    version_name: str


def task_not_found(task_id: int) -> AppError:
    return AppError(404, "task_not_found", f"Task {task_id} not found")


def _view_query():
    return (
        select(Task, Pipeline.name, PipelineVersion.version_name)
        .join(PipelineVersion, PipelineVersion.id == Task.pipeline_version_id)
        .join(Pipeline, Pipeline.id == PipelineVersion.pipeline_id)
    )


async def load_task(
    db: AsyncSession, task_id: int, user: User | None
) -> tuple[TaskView, WorkspaceAccess]:
    """A task and the user's rights in its workspace. 404 for people who
    may not see tasks there (also in public workspaces: only works are
    public)."""
    row = (await db.execute(_view_query().where(Task.id == task_id))).first()
    if row is None:
        raise task_not_found(task_id)
    task, pipeline_name, version_name = row
    try:
        access = await load_access(db, task.workspace_id, user)
    except AppError:
        raise task_not_found(task_id) from None
    if not access.can_see_inside:
        raise task_not_found(task_id)
    return TaskView(task, pipeline_name, version_name), access


async def list_tasks(
    db: AsyncSession,
    access: WorkspaceAccess,
    status: TaskStatus | None,
    limit: int,
    offset: int,
) -> list[TaskView]:
    require_inside(access)
    query = _view_query().where(Task.workspace_id == access.workspace.id)
    if status is not None:
        query = query.where(Task.status == status)
    # Uses the index on (workspace_id, created_at DESC).
    query = query.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit).offset(offset)
    return [TaskView(*row) for row in await db.execute(query)]


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    kind: str


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlanStep, ...]
    rerun_start: int  # where a revision after a rejected review starts

    def step_at(self, step_index: int) -> PlanStep | None:
        """The step of a task_steps row. Rows 0..n-1 are the pipeline
        steps; each revision adds the steps from rerun_start to the end
        (the same mapping as the worker, runner.step_rows)."""
        n = len(self.steps)
        if step_index < n:
            return self.steps[step_index]
        tail = n - self.rerun_start
        if tail <= 0:
            return None
        return self.steps[self.rerun_start + (step_index - n) % tail]


@lru_cache(maxsize=64)
def _read_plan(file_path: str, file_hash: str) -> Plan:
    """A version file never changes (its hash is in the DB), so the plan
    can be cached by path and hash."""
    pipeline = load_pipeline(Path(file_path))
    steps = tuple(PlanStep(step.id, step.kind) for step in pipeline.steps)
    return Plan(steps, rerun_start(pipeline))


async def pipeline_plan(db: AsyncSession, version_id: int) -> Plan:
    """All steps of a pipeline version, also those that have not run yet.
    Empty if the file cannot be read (the task page still works)."""
    version = await db.get(PipelineVersion, version_id)
    if version is None:
        return Plan((), 0)
    try:
        return _read_plan(version.file_path, version.file_hash)
    except PipelineError as exc:
        log.warning("Cannot read the plan of pipeline version %s: %s", version_id, exc)
        return Plan((), 0)


async def list_steps(db: AsyncSession, task_id: int) -> list[TaskStep]:
    query = select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.step_index)
    return list(await db.scalars(query))


async def _newest_version(db: AsyncSession, pipeline_id: int) -> PipelineVersion:
    version = await db.scalar(
        select(PipelineVersion)
        .where(PipelineVersion.pipeline_id == pipeline_id)
        .order_by(PipelineVersion.version_code.desc())
        .limit(1)
    )
    if version is None:
        exists = await db.get(Pipeline, pipeline_id)
        if exists is None:
            raise AppError(404, "pipeline_not_found", f"Pipeline {pipeline_id} not found")
        raise AppError(
            409, "pipeline_has_no_versions", f"Pipeline {exists.name} has no versions yet"
        )
    return version


async def _check_model(db: AsyncSession, model_id: int) -> None:
    model = await db.get(Model, model_id)
    if model is None:
        raise AppError(404, "model_not_found", f"Model {model_id} not found")
    if not model.available:
        raise AppError(409, "model_unavailable", f"Model {model.name} is not available")


async def _check_reviewer(db: AsyncSession, access: WorkspaceAccess, user_id: int | None) -> None:
    """The reviewer must be the owner or a member of the workspace."""
    if user_id is None or user_id == access.workspace.owner_id:
        return
    is_member = await db.scalar(
        select(Membership.user_id).where(
            Membership.workspace_id == access.workspace.id, Membership.user_id == user_id
        )
    )
    if is_member is None:
        raise AppError(409, "reviewer_not_member", f"User {user_id} is not in this workspace")


async def create_task(
    db: AsyncSession,
    access: WorkspaceAccess,
    *,
    title: str,
    input: str,
    pipeline_id: int,
    model_id: int,
    reviewer_id: int | None,
    reviewer_given: bool,
) -> TaskView:
    """New tasks use the newest pipeline version. Reviewer = the creator
    unless another one is given."""
    require_task_editor(access)
    require_not_archived(access)
    user = access.user
    assert user is not None  # require_task_editor needs a logged-in user
    version = await _newest_version(db, pipeline_id)
    await _check_model(db, model_id)
    if not reviewer_given:
        reviewer_id = user.id
    await _check_reviewer(db, access, reviewer_id)

    task = Task(
        workspace_id=access.workspace.id,
        pipeline_version_id=version.id,
        model_id=model_id,
        title=title,
        input=input,
        created_by=user.id,
        reviewer_id=reviewer_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    pipeline = await db.get(Pipeline, pipeline_id)
    return TaskView(task, pipeline.name, version.version_name)


async def update_task(
    db: AsyncSession, view: TaskView, access: WorkspaceAccess, changes: dict
) -> TaskView:
    """title, input and model only while the task is a draft; the
    reviewer until the task is done or cancelled."""
    require_task_editor(access)
    require_not_archived(access)
    task = view.task
    content = {"title", "input", "model_id"} & changes.keys()
    if content and task.status != TaskStatus.DRAFT:
        raise AppError(409, "task_not_draft", "Only a draft can be edited")
    if "reviewer_id" in changes:
        if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            raise AppError(409, "task_finished", "The task is finished")
        await _check_reviewer(db, access, changes["reviewer_id"])
    if "model_id" in changes:
        await _check_model(db, changes["model_id"])
    for field, value in changes.items():
        setattr(task, field, value)
    await db.commit()
    return view


async def queue(db: AsyncSession, view: TaskView, access: WorkspaceAccess) -> TaskView:
    require_task_editor(access)
    require_not_archived(access)
    if view.task.status != TaskStatus.DRAFT:
        raise AppError(409, "task_not_draft", "Only a draft can be queued")
    view.task.status = TaskStatus.QUEUED
    await db.commit()
    return view


async def cancel(db: AsyncSession, view: TaskView, access: WorkspaceAccess) -> TaskView:
    """The worker sees the new status before its next step and stops."""
    require_task_editor(access)
    if view.task.status not in CANCELLABLE:
        raise AppError(
            409, "task_not_cancellable", f"A {view.task.status} task cannot be cancelled"
        )
    view.task.status = TaskStatus.CANCELLED
    view.task.finished_at = func.now()
    await db.commit()
    await db.refresh(view.task)
    return view


async def delete_task(db: AsyncSession, view: TaskView, access: WorkspaceAccess) -> None:
    """Steps, calls, reviews and the work go with it (CASCADE). A
    published work blocks the delete (RESTRICT)."""
    require_task_editor(access)
    task = view.task
    if task.status == TaskStatus.RUNNING:
        raise AppError(409, "task_running", "Cancel the task first")
    try:
        await db.delete(task)
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            409,
            "task_published",
            "The work of this task is published; remove the publication first",
        ) from exc
    activity.record(
        db,
        "task_deleted",
        actor=access.user,
        workspace_id=access.workspace.id,
        target_type="task",
        target_id=task.id,
        target_label=task.title,
    )
    await db.commit()
