"""Publishers and publications (results_and_evidence.md).

A publisher is a public signature; a publication shows a work under it,
without showing the workspace. Rules (backend_spec.md, section 6): only
the workspace owner publishes, only an accepted (done) task, only under
a publisher they own. A work is published once (publications.work_id is
unique). Publications are public.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Publication, Publisher, Task, User, Work
from autolab.db.models.enums import TaskStatus
from autolab.errors import AppError
from autolab.services import activity
from autolab.services.permissions import forbidden, load_access


def publisher_not_found(publisher_id: int) -> AppError:
    return AppError(404, "publisher_not_found", f"Publisher {publisher_id} not found")


def publication_not_found(publication_id: int) -> AppError:
    return AppError(404, "publication_not_found", f"Publication {publication_id} not found")


async def create_publisher(
    db: AsyncSession, user: User, *, name: str, description: str | None
) -> Publisher:
    publisher = Publisher(name=name, description=description, owner_id=user.id)
    db.add(publisher)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "publisher_exists", f"The name {name!r} is taken") from exc
    activity.record(
        db,
        "publisher_created",
        actor=user,
        target_type="publisher",
        target_id=publisher.id,
        target_label=name,
    )
    await db.commit()
    return publisher


async def my_publishers(db: AsyncSession, user: User) -> list[Publisher]:
    query = select(Publisher).where(Publisher.owner_id == user.id).order_by(Publisher.name)
    return list(await db.scalars(query))


async def get_publisher(db: AsyncSession, publisher_id: int) -> Publisher:
    publisher = await db.get(Publisher, publisher_id)
    if publisher is None:
        raise publisher_not_found(publisher_id)
    return publisher


async def publish(
    db: AsyncSession,
    user: User,
    *,
    task_id: int,
    publisher_id: int,
    title: str,
    description: str | None,
) -> Publication:
    task = await db.get(Task, task_id)
    work = await db.get(Work, task_id)
    if task is None or work is None:
        raise AppError(404, "work_not_found", f"Task {task_id} has no work")
    access = await load_access(db, task.workspace_id, user)  # 404 for outsiders
    if not access.is_owner:
        raise forbidden("Only the owner of the workspace can publish its works")
    if task.status != TaskStatus.DONE:
        raise AppError(409, "task_not_accepted", "Only an accepted work can be published")
    publisher = await get_publisher(db, publisher_id)
    if publisher.owner_id != user.id:
        raise forbidden("You can publish only under your own publisher")

    publication = Publication(
        work_id=task_id, publisher_id=publisher_id, title=title, description=description
    )
    db.add(publication)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "already_published", "This work is already published") from exc
    activity.record(
        db,
        "work_published",
        actor=user,
        workspace_id=task.workspace_id,
        target_type="publication",
        target_id=publication.id,
        target_label=title,
        details={"publisher": publisher.name},
    )
    await db.commit()
    await db.refresh(publication)
    return publication


async def list_publications(
    db: AsyncSession, publisher_id: int | None, limit: int, offset: int
) -> list[tuple[Publication, Publisher]]:
    """The public feed, newest first (index on (publisher_id, published_at))."""
    query = select(Publication, Publisher).join(Publisher, Publisher.id == Publication.publisher_id)
    if publisher_id is not None:
        query = query.where(Publication.publisher_id == publisher_id)
    query = query.order_by(Publication.published_at.desc(), Publication.id.desc())
    return [(p, pub) for p, pub in await db.execute(query.limit(limit).offset(offset))]


async def get_publication(db: AsyncSession, publication_id: int) -> tuple[Publication, Publisher]:
    row = (
        await db.execute(
            select(Publication, Publisher)
            .join(Publisher, Publisher.id == Publication.publisher_id)
            .where(Publication.id == publication_id)
        )
    ).first()
    if row is None:
        raise publication_not_found(publication_id)
    return row[0], row[1]


async def delete_publication(db: AsyncSession, publication_id: int) -> None:
    """Admins only (there is no 'withdraw' yet, see BACKLOG.md). After
    this, the task can be deleted again (publications.work_id is RESTRICT)."""
    publication = await db.get(Publication, publication_id)
    if publication is None:
        raise publication_not_found(publication_id)
    await db.delete(publication)
    await db.commit()
