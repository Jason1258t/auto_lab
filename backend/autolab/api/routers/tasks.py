"""Tasks. No worker yet: `queue` only sets the status."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from autolab.api.deps import CurrentPrincipal, DbSession
from autolab.api.schemas.tasks import (
    PlanStepOut,
    TaskDetailOut,
    TaskIn,
    TaskOut,
    TaskStepOut,
    TaskUpdate,
)
from autolab.db.models import TaskStep
from autolab.db.models.enums import TaskStatus
from autolab.errors import AppError
from autolab.services import tasks as tasks_service
from autolab.services.permissions import load_access
from autolab.services.tasks import TaskView

router = APIRouter(tags=["tasks"])


def task_out(view: TaskView) -> TaskOut:
    task = view.task
    return TaskOut(
        id=task.id,
        workspace_id=task.workspace_id,
        title=task.title,
        input=task.input,
        status=task.status,
        pipeline_name=view.pipeline_name,
        pipeline_version=view.version_name,
        pipeline_version_id=task.pipeline_version_id,
        model_id=task.model_id,
        created_by=task.created_by,
        reviewer_id=task.reviewer_id,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


@router.get("/workspaces/{workspace_id}/tasks")
async def list_tasks(
    workspace_id: int,
    principal: CurrentPrincipal,
    db: DbSession,
    status: TaskStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskOut]:
    access = await load_access(db, workspace_id, principal.user)
    views = await tasks_service.list_tasks(db, access, status, limit, offset)
    return [task_out(v) for v in views]


@router.post("/workspaces/{workspace_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    workspace_id: int, body: TaskIn, principal: CurrentPrincipal, db: DbSession
) -> TaskOut:
    access = await load_access(db, workspace_id, principal.user)
    view = await tasks_service.create_task(
        db,
        access,
        title=body.title,
        input=body.input,
        pipeline_id=body.pipeline_id,
        model_id=body.model_id,
        reviewer_id=body.reviewer_id,
        reviewer_given="reviewer_id" in body.model_fields_set,
    )
    return task_out(view)


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, principal: CurrentPrincipal, db: DbSession) -> TaskDetailOut:
    view, _ = await tasks_service.load_task(db, task_id, principal.user)
    steps = await tasks_service.list_steps(db, task_id)
    plan = await tasks_service.pipeline_plan(db, view.task.pipeline_version_id)
    return TaskDetailOut(
        **task_out(view).model_dump(),
        plan=[PlanStepOut(step_id=p.step_id, kind=p.kind) for p in plan.steps],
        steps=[step_out(s, plan) for s in steps],
    )


def step_out(step: TaskStep, plan: tasks_service.Plan) -> TaskStepOut:
    out = TaskStepOut.model_validate(step)
    named = plan.step_at(step.step_index)
    if named is not None:
        out.step_id, out.kind = named.step_id, named.kind
    return out


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int, body: TaskUpdate, principal: CurrentPrincipal, db: DbSession
) -> TaskOut:
    changes = body.model_dump(include=body.model_fields_set)
    for field in ("title", "input", "model_id"):
        if field in changes and changes[field] is None:
            raise AppError(422, "validation_error", f"{field} cannot be null")
    view, access = await tasks_service.load_task(db, task_id, principal.user)
    return task_out(await tasks_service.update_task(db, view, access, changes))


@router.post("/tasks/{task_id}/queue")
async def queue(task_id: int, principal: CurrentPrincipal, db: DbSession) -> TaskOut:
    view, access = await tasks_service.load_task(db, task_id, principal.user)
    return task_out(await tasks_service.queue(db, view, access))


@router.post("/tasks/{task_id}/cancel")
async def cancel(task_id: int, principal: CurrentPrincipal, db: DbSession) -> TaskOut:
    view, access = await tasks_service.load_task(db, task_id, principal.user)
    return task_out(await tasks_service.cancel(db, view, access))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, principal: CurrentPrincipal, db: DbSession) -> None:
    view, access = await tasks_service.load_task(db, task_id, principal.user)
    await tasks_service.delete_task(db, view, access)
