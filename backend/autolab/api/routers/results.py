"""Reviews, works and LLM calls of a task."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from autolab.api.deps import CurrentPrincipal, DbSession, OptionalUser, SettingsDep
from autolab.db.models.enums import FinishReason, LlmCallStatus, ReviewResult, TaskStatus
from autolab.logstore import LogStore
from autolab.services import reviews as reviews_service
from autolab.services import works as works_service
from autolab.services.permissions import load_access
from autolab.services.tasks import load_task

router = APIRouter(tags=["results"])


def get_log_store(request: Request) -> LogStore:
    return request.app.state.log_store


LogStoreDep = Annotated[LogStore, Depends(get_log_store)]


class ReviewIn(BaseModel):
    result: ReviewResult
    comment: str | None = Field(default=None, max_length=5000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    reviewer_id: int | None
    result: ReviewResult
    comment: str | None
    created_at: datetime


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim: str
    quote: str
    placement: str | None


class SourceOut(BaseModel):
    id: int
    title: str
    kind: str
    location: str
    accessed_at: datetime
    quotes: list[QuoteOut]


class WorkOut(BaseModel):
    task_id: int
    workspace_id: int
    title: str
    task_status: TaskStatus
    summary: str | None
    text: str  # markdown
    updated_at: datetime
    sources: list[SourceOut]


class WorkListItem(BaseModel):
    task_id: int
    title: str
    task_status: TaskStatus
    summary: str | None
    updated_at: datetime


class CallOut(BaseModel):
    id: int
    step_index: int
    attempt: int
    status: LlmCallStatus
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: FinishReason | None
    valid_json: bool | None


# The log document from the log store (worker/gateway/base.py as_log and
# llm_manager). Extra keys are kept, so an older or newer log still loads.
class LogMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str


class LogRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[LogMessage]
    # JSON schema the answer must match, and generation parameters.
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    params: dict[str, Any] = {}


class LogResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    raw: dict[str, Any] | None = None


class CallLogOut(BaseModel):
    """The full prompt and the model's answer (None while it runs, or if
    the call failed). Texts may contain fetched web pages: untrusted data,
    show them only as plain text."""

    model_config = ConfigDict(serialize_by_alias=True)

    request: LogRequest
    response: LogResponse | None = None
    created_at: str
    answered_at: str | None = None


@router.get("/tasks/{task_id}/reviews")
async def list_reviews(task_id: int, principal: CurrentPrincipal, db: DbSession) -> list[ReviewOut]:
    view, access = await load_task(db, task_id, principal.user)
    return [
        ReviewOut.model_validate(r) for r in await reviews_service.list_reviews(db, view, access)
    ]


@router.post("/tasks/{task_id}/reviews", status_code=status.HTTP_201_CREATED)
async def add_review(
    task_id: int, body: ReviewIn, principal: CurrentPrincipal, db: DbSession, settings: SettingsDep
) -> ReviewOut:
    view, access = await load_task(db, task_id, principal.user)
    review = await reviews_service.add_review(db, settings, view, access, body.result, body.comment)
    return ReviewOut.model_validate(review)


@router.get("/tasks/{task_id}/work")
async def get_work(task_id: int, db: DbSession, user: OptionalUser) -> WorkOut:
    view = await works_service.get_work(db, task_id, user)
    return WorkOut(
        task_id=view.task.id,
        workspace_id=view.task.workspace_id,
        title=view.task.title,
        task_status=view.task.status,
        summary=view.work.summary,
        text=view.text,
        updated_at=view.work.updated_at,
        sources=[
            SourceOut(
                id=s.source.id,
                title=s.source.title,
                kind=s.source.kind,
                location=s.source.location,
                accessed_at=s.source.accessed_at,
                quotes=[QuoteOut.model_validate(q) for q in s.quotes],
            )
            for s in view.sources
        ],
    )


@router.get("/workspaces/{workspace_id}/works")
async def list_works(
    workspace_id: int,
    db: DbSession,
    user: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkListItem]:
    access = await load_access(db, workspace_id, user)
    return [
        WorkListItem(
            task_id=task.id,
            title=task.title,
            task_status=task.status,
            summary=work.summary,
            updated_at=work.updated_at,
        )
        for task, work in await works_service.list_works(db, access, limit, offset)
    ]


@router.get("/tasks/{task_id}/calls")
async def list_calls(task_id: int, principal: CurrentPrincipal, db: DbSession) -> list[CallOut]:
    return [
        CallOut(
            id=call.id,
            step_index=call.step_index,
            attempt=call.attempt,
            status=call.status,
            error=call.error,
            created_at=call.created_at,
            started_at=call.started_at,
            finished_at=call.finished_at,
            input_tokens=response.input_tokens if response else None,
            output_tokens=response.output_tokens if response else None,
            finish_reason=response.finish_reason if response else None,
            valid_json=response.valid_json if response else None,
        )
        for call, response in await works_service.list_calls(db, task_id, principal.user)
    ]


@router.get("/calls/{call_id}/log")
async def get_call_log(
    call_id: int, principal: CurrentPrincipal, db: DbSession, log_store: LogStoreDep
) -> CallLogOut:
    """The full prompt and the model's answer."""
    log = await works_service.get_call_log(db, log_store, call_id, principal.user)
    return CallLogOut.model_validate(log)
