"""Workspaces, members, roles and the workspace activity log."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from autolab.api.deps import CurrentPrincipal, DbSession, OptionalUser
from autolab.api.schemas.workspaces import (
    ActivityEventOut,
    MemberIn,
    MemberOut,
    WorkspaceIn,
    WorkspaceOut,
    WorkspaceUpdate,
)
from autolab.db.models import User, Workspace
from autolab.services import members as members_service
from autolab.services import workspaces as workspaces_service
from autolab.services.permissions import WorkspaceAccess, load_access

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def workspace_out(workspace: Workspace, user: User | None, roles: list[str]) -> WorkspaceOut:
    out = WorkspaceOut.model_validate(workspace)
    out.is_owner = user is not None and workspace.owner_id == user.id
    out.my_roles = roles
    return out


def access_out(access: WorkspaceAccess) -> WorkspaceOut:
    return workspace_out(access.workspace, access.user, sorted(access.roles))


def member_out(member: members_service.Member) -> MemberOut:
    return MemberOut(
        user_id=member.user.id,
        username=member.user.username,
        display_name=member.user.display_name,
        roles=member.roles,
    )


@router.get("")
async def list_workspaces(
    db: DbSession,
    user: OptionalUser,
    scope: workspaces_service.Scope = "mine",
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[WorkspaceOut]:
    found = await workspaces_service.list_workspaces(db, user, scope, limit, offset)
    roles = await workspaces_service.my_roles(db, user, [w.id for w in found]) if user else {}
    return [workspace_out(w, user, roles.get(w.id, [])) for w in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceIn, principal: CurrentPrincipal, db: DbSession
) -> WorkspaceOut:
    workspace = await workspaces_service.create_workspace(
        db, principal.user, name=body.name, description=body.description
    )
    return workspace_out(workspace, principal.user, [])


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: int, db: DbSession, user: OptionalUser) -> WorkspaceOut:
    return access_out(await load_access(db, workspace_id, user))


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: int, body: WorkspaceUpdate, principal: CurrentPrincipal, db: DbSession
) -> WorkspaceOut:
    access = await load_access(db, workspace_id, principal.user)
    await workspaces_service.update_workspace(
        db, access, name=body.name, description=body.description
    )
    return access_out(access)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: int, principal: CurrentPrincipal, db: DbSession) -> None:
    access = await load_access(db, workspace_id, principal.user)
    await workspaces_service.delete_workspace(db, access)


@router.post("/{workspace_id}/archive")
async def archive(workspace_id: int, principal: CurrentPrincipal, db: DbSession) -> WorkspaceOut:
    access = await load_access(db, workspace_id, principal.user)
    workspace = await workspaces_service.archive(db, access)
    return workspace_out(workspace, principal.user, [])


@router.post("/{workspace_id}/unarchive")
async def unarchive(workspace_id: int, principal: CurrentPrincipal, db: DbSession) -> WorkspaceOut:
    access = await load_access(db, workspace_id, principal.user)
    await workspaces_service.unarchive(db, access)
    return access_out(access)


@router.post("/{workspace_id}/make-public")
async def make_public(
    workspace_id: int, principal: CurrentPrincipal, db: DbSession
) -> WorkspaceOut:
    access = await load_access(db, workspace_id, principal.user)
    await workspaces_service.make_public(db, access)
    return access_out(access)


@router.post("/{workspace_id}/take")
async def take(workspace_id: int, principal: CurrentPrincipal, db: DbSession) -> WorkspaceOut:
    workspace = await workspaces_service.take(db, principal.user, workspace_id)
    return workspace_out(workspace, principal.user, [])


# --- Members and roles ---


@router.get("/{workspace_id}/members")
async def list_members(workspace_id: int, db: DbSession, user: OptionalUser) -> list[MemberOut]:
    access = await load_access(db, workspace_id, user)
    return [member_out(m) for m in await members_service.list_members(db, access)]


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: int, body: MemberIn, principal: CurrentPrincipal, db: DbSession
) -> MemberOut:
    access = await load_access(db, workspace_id, principal.user)
    return member_out(await members_service.add_member(db, access, body.username_or_email))


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: int, user_id: int, principal: CurrentPrincipal, db: DbSession
) -> None:
    access = await load_access(db, workspace_id, principal.user)
    await members_service.remove_member(db, access, user_id)


@router.put("/{workspace_id}/members/{user_id}/roles/{role}")
async def grant_role(
    workspace_id: int, user_id: int, role: str, principal: CurrentPrincipal, db: DbSession
) -> MemberOut:
    access = await load_access(db, workspace_id, principal.user)
    return member_out(await members_service.grant_role(db, access, user_id, role))


@router.delete("/{workspace_id}/members/{user_id}/roles/{role}")
async def revoke_role(
    workspace_id: int, user_id: int, role: str, principal: CurrentPrincipal, db: DbSession
) -> MemberOut:
    access = await load_access(db, workspace_id, principal.user)
    return member_out(await members_service.revoke_role(db, access, user_id, role))


# --- Activity log ---


@router.get("/{workspace_id}/activity")
async def list_activity(
    workspace_id: int,
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[ActivityEventOut]:
    access = await load_access(db, workspace_id, principal.user)
    events = await workspaces_service.list_activity(db, access, limit, offset)
    return [ActivityEventOut.model_validate(e) for e in events]
