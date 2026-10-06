"""Publishers and publications. Reading is public; the workspace is never
shown."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field

from autolab.api.deps import AdminPrincipal, CurrentPrincipal, DbSession
from autolab.api.routers.results import QuoteOut, SourceOut
from autolab.db.models import Task, Work
from autolab.services import publications as publications_service
from autolab.services.works import work_content

router = APIRouter(tags=["publications"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


class PublisherIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class PublisherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class PublicationIn(BaseModel):
    task_id: int  # the work = the task's result
    publisher_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)


class PublicationOut(BaseModel):
    id: int
    title: str
    description: str | None
    published_at: datetime
    publisher: PublisherOut


class PublicationDetail(PublicationOut):
    text: str  # markdown of the work
    sources: list[SourceOut]


def publication_out(publication, publisher) -> PublicationOut:
    return PublicationOut(
        id=publication.id,
        title=publication.title,
        description=publication.description,
        published_at=publication.published_at,
        publisher=PublisherOut.model_validate(publisher),
    )


@router.post("/publishers", status_code=status.HTTP_201_CREATED)
async def create_publisher(
    body: PublisherIn, principal: CurrentPrincipal, db: DbSession
) -> PublisherOut:
    publisher = await publications_service.create_publisher(
        db, principal.user, name=body.name, description=body.description
    )
    return PublisherOut.model_validate(publisher)


@router.get("/publishers/mine")
async def my_publishers(principal: CurrentPrincipal, db: DbSession) -> list[PublisherOut]:
    return [
        PublisherOut.model_validate(p)
        for p in await publications_service.my_publishers(db, principal.user)
    ]


@router.get("/publishers/{publisher_id}")
async def get_publisher(publisher_id: int, db: DbSession) -> PublisherOut:
    return PublisherOut.model_validate(await publications_service.get_publisher(db, publisher_id))


@router.post("/publications", status_code=status.HTTP_201_CREATED)
async def publish(
    body: PublicationIn, principal: CurrentPrincipal, db: DbSession
) -> PublicationOut:
    publication = await publications_service.publish(
        db,
        principal.user,
        task_id=body.task_id,
        publisher_id=body.publisher_id,
        title=body.title,
        description=body.description,
    )
    publisher = await publications_service.get_publisher(db, publication.publisher_id)
    return publication_out(publication, publisher)


@router.get("/publications")
async def list_publications(
    db: DbSession,
    publisher_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PublicationOut]:
    rows = await publications_service.list_publications(db, publisher_id, limit, offset)
    return [publication_out(p, pub) for p, pub in rows]


@router.get("/publications/{publication_id}")
async def get_publication(publication_id: int, db: DbSession) -> PublicationDetail:
    publication, publisher = await publications_service.get_publication(db, publication_id)
    work = await db.get(Work, publication.work_id)
    view = await work_content(db, await db.get(Task, publication.work_id), work)
    return PublicationDetail(
        **publication_out(publication, publisher).model_dump(),
        text=view.text,
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


@admin_router.delete("/publications/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_publication(publication_id: int, _: AdminPrincipal, db: DbSession) -> None:
    await publications_service.delete_publication(db, publication_id)
