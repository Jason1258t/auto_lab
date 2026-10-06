"""Request and response bodies for tasks."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from autolab.db.models.enums import TaskStatus, TaskStepStatus


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    input: str = Field(min_length=1, max_length=20_000)
    pipeline_id: int
    model_id: int
    # Not sent = the creator reviews. null = no assigned reviewer (any
    # editor or reviewer of the workspace can review).
    reviewer_id: int | None = None


class TaskUpdate(BaseModel):
    """Only the fields that are sent are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    input: str | None = Field(default=None, min_length=1, max_length=20_000)
    model_id: int | None = None
    reviewer_id: int | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    title: str
    input: str
    status: TaskStatus
    pipeline_name: str
    pipeline_version: str
    pipeline_version_id: int
    model_id: int
    created_by: int | None
    reviewer_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_index: int
    status: TaskStepStatus
    summary: str | None
    review_id: int | None
    started_at: datetime | None
    finished_at: datetime | None


class TaskDetailOut(TaskOut):
    steps: list[TaskStepOut]
