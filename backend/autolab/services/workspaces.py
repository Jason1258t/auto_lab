"""Workspaces: create, list, edit, archive, make public, take, delete.
Each change is one transaction together with its activity event."""

import asyncio
from typing import Literal

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import ActivityEvent, Membership, Role, User, Workspace
from autolab.db.models.enums import WorkspaceVisibility
from autolab.errors import AppError
from autolab.services import activity
from autolab.services.files import remove_workspace_folder
from autolab.services.permissions import (
    WorkspaceAccess,
    forbidden,
    require_not_archived,
    require_owner,
    workspace_not_found,
)

Scope = Literal["mine", "public", "free"]


def _event(db: AsyncSession, action: str, actor: User, workspace: Workspace) -> None:
    activity.record(
        db,
        action,
        actor=actor,
        workspace_id=workspace.id,
        target_type="workspace",
        target_id=workspace.id,
        target_label=workspace.name,
    )


async def list_workspaces(
    db: AsyncSession, user: User | None, scope: Scope, limit: int, offset: int
) -> list[Workspace]:
    """mine: owned or member of. public: all public ones. free: public,
    archived, without owner (anyone can take them)."""
    query = select(Workspace)
    if scope == "mine":
        if user is None:
            return []
        member_of = select(Membership.workspace_id).where(Membership.user_id == user.id)
        query = query.where(or_(Workspace.owner_id == user.id, Workspace.id.in_(member_of)))
    elif scope == "public":
        query = query.where(Workspace.visibility == WorkspaceVisibility.PUBLIC)
    else:
        query = query.where(
            Workspace.visibility == WorkspaceVisibility.PUBLIC,
            Workspace.archived_at.is_not(None),
            Workspace.owner_id.is_(None),
        )
    query = query.order_by(Workspace.created_at.desc(), Workspace.id.desc())
    return list(await db.scalars(query.limit(limit).offset(offset)))


async def my_roles(db: AsyncSession, user: User, workspace_ids: list[int]) -> dict[int, list[str]]:
    """The user's roles in many workspaces, in one query."""
    rows = await db.execute(
        select(Membership.workspace_id, Role.name)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.user_id == user.id, Membership.workspace_id.in_(workspace_ids))
        .order_by(Role.name)
    )
    roles: dict[int, list[str]] = {}
    for workspace_id, name in rows:
        roles.setdefault(workspace_id, []).append(name)
    return roles


async def create_workspace(
    db: AsyncSession, user: User, *, name: str, description: str | None
) -> Workspace:
    description = (description or "").strip() or None  # "" = no description
    workspace = Workspace(name=name, description=description, created_by=user.id, owner_id=user.id)
    db.add(workspace)
    await db.commit()
    return workspace


async def update_workspace(
    db: AsyncSession, access: WorkspaceAccess, *, name: str | None, description: str | None
) -> Workspace:
    require_owner(access)
    require_not_archived(access)
    workspace = access.workspace
    if name is not None:
        workspace.name = name
    if description is not None:  # None = keep it; "" = remove it
        workspace.description = description.strip() or None
    await db.commit()
    return workspace


async def archive(db: AsyncSession, access: WorkspaceAccess) -> Workspace:
    """Read-only from now on. All memberships are deleted. A public
    workspace also loses its owner, so anyone can take it."""
    actor = require_owner(access)
    require_not_archived(access)
    workspace = access.workspace
    workspace.archived_at = func.now()
    if workspace.visibility == WorkspaceVisibility.PUBLIC:
        workspace.owner_id = None
    await db.execute(delete(Membership).where(Membership.workspace_id == workspace.id))
    _event(db, "archived", actor, workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def unarchive(db: AsyncSession, access: WorkspaceAccess) -> Workspace:
    """Only for private workspaces. A public archived one has no owner;
    it can only be taken."""
    actor = require_owner(access)
    workspace = access.workspace
    if not access.is_archived:
        raise AppError(409, "workspace_not_archived", "The workspace is not archived")
    workspace.archived_at = None
    _event(db, "unarchived", actor, workspace)
    await db.commit()
    return workspace


async def make_public(db: AsyncSession, access: WorkspaceAccess) -> Workspace:
    """One way only: a DB trigger blocks public -> private."""
    actor = require_owner(access)
    require_not_archived(access)
    workspace = access.workspace
    if workspace.visibility == WorkspaceVisibility.PUBLIC:
        raise AppError(409, "already_public", "The workspace is already public")
    workspace.visibility = WorkspaceVisibility.PUBLIC
    _event(db, "made_public", actor, workspace)
    await db.commit()
    return workspace


async def take(db: AsyncSession, user: User, workspace_id: int) -> Workspace:
    """Take a free workspace (public, archived, no owner). One UPDATE, so
    if two people try at the same time, only the first one wins."""
    workspace = await db.scalar(
        update(Workspace)
        .where(
            Workspace.id == workspace_id,
            Workspace.owner_id.is_(None),
            Workspace.visibility == WorkspaceVisibility.PUBLIC,
            Workspace.archived_at.is_not(None),
        )
        .values(owner_id=user.id, archived_at=None)
        .returning(Workspace)
    )
    if workspace is None:
        exists = await db.scalar(
            select(Workspace.id).where(
                Workspace.id == workspace_id, Workspace.visibility == WorkspaceVisibility.PUBLIC
            )
        )
        if exists is None:
            raise workspace_not_found(workspace_id)
        raise AppError(409, "workspace_not_free", "Someone else owns this workspace")
    _event(db, "workspace_taken", user, workspace)
    await db.commit()
    return workspace


async def delete_workspace(db: AsyncSession, settings: Settings, access: WorkspaceAccess) -> None:
    """Only a workspace without tasks can be deleted (tasks.workspace_id
    is RESTRICT). Otherwise: archive it. Its files are deleted too."""
    actor = require_owner(access)
    workspace = access.workspace
    try:  # memberships go with it (CASCADE)
        await db.delete(workspace)
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            409, "workspace_not_empty", "Only an empty workspace can be deleted; archive it instead"
        ) from exc
    _event(db, "workspace_deleted", actor, workspace)
    await db.commit()
    await asyncio.to_thread(remove_workspace_folder, settings, workspace.id)


async def list_activity(
    db: AsyncSession, access: WorkspaceAccess, limit: int, offset: int
) -> list[ActivityEvent]:
    """The workspace log, newest first (uses the index on
    (workspace_id, occurred_at DESC))."""
    if not access.can_read_activity:
        raise forbidden("Only the owner and editors can read the activity log")
    query = (
        select(ActivityEvent)
        .where(ActivityEvent.workspace_id == access.workspace.id)
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await db.scalars(query))
