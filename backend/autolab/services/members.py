"""Members and roles of a workspace.

Add a person = give them the 'member' role (owner only). Remove a
person = delete all their roles in the workspace. 'editor' and
'reviewer' are granted on top of 'member' (rules: permissions.py).
"""

from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Membership, Role, User
from autolab.errors import AppError
from autolab.services import activity
from autolab.services.permissions import (
    MEMBER,
    ROLE_GRANTERS,
    WorkspaceAccess,
    forbidden,
    require_inside,
    require_not_archived,
    require_owner,
)


@dataclass(frozen=True)
class Member:
    user: User
    roles: list[str]


def member_not_found(user_id: int) -> AppError:
    return AppError(404, "member_not_found", f"User {user_id} is not a member")


async def _role_id(db: AsyncSession, name: str) -> int:
    role_id = await db.scalar(select(Role.id).where(Role.name == name))
    if role_id is None:
        raise AppError(404, "role_not_found", f"Role {name!r} not found")
    return role_id


async def _roles_of(db: AsyncSession, workspace_id: int, user_id: int) -> set[str]:
    names = await db.scalars(
        select(Role.name)
        .join(Membership, Membership.role_id == Role.id)
        .where(Membership.workspace_id == workspace_id, Membership.user_id == user_id)
    )
    return set(names)


def _event(
    db: AsyncSession, action: str, access: WorkspaceAccess, user: User, role: str | None = None
) -> None:
    activity.record(
        db,
        action,
        actor=access.user,
        workspace_id=access.workspace.id,
        target_type="user",
        target_id=user.id,
        target_label=user.username,
        details={"role": role} if role else None,
    )


async def list_members(db: AsyncSession, access: WorkspaceAccess) -> list[Member]:
    require_inside(access)
    rows = await db.execute(
        select(User, func.array_agg(Role.name).label("roles"))
        .join(Membership, Membership.user_id == User.id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.workspace_id == access.workspace.id)
        .group_by(User.id)
        .order_by(User.username)
    )
    return [Member(user=user, roles=sorted(roles)) for user, roles in rows]


async def add_member(db: AsyncSession, access: WorkspaceAccess, username_or_email: str) -> Member:
    require_owner(access)
    require_not_archived(access)
    user = await db.scalar(
        select(User).where(
            or_(
                User.username == username_or_email,
                func.lower(User.email) == username_or_email.lower(),
            )
        )
    )
    if user is None:
        raise AppError(404, "user_not_found", f"No user {username_or_email!r}")
    if user.id == access.workspace.owner_id:
        raise AppError(409, "already_owner", "The owner is not added as a member")
    if MEMBER in await _roles_of(db, access.workspace.id, user.id):
        raise AppError(409, "already_member", f"{user.username} is already a member")

    db.add(
        Membership(
            workspace_id=access.workspace.id, user_id=user.id, role_id=await _role_id(db, MEMBER)
        )
    )
    _event(db, "member_added", access, user)
    await db.commit()
    return Member(user=user, roles=[MEMBER])


async def remove_member(db: AsyncSession, access: WorkspaceAccess, user_id: int) -> None:
    """Removes the person with all their roles."""
    require_owner(access)
    user = await db.get(User, user_id)
    removed = await db.execute(
        delete(Membership).where(
            Membership.workspace_id == access.workspace.id, Membership.user_id == user_id
        )
    )
    if user is None or removed.rowcount == 0:
        raise member_not_found(user_id)
    _event(db, "member_removed", access, user)
    await db.commit()


async def leave(db: AsyncSession, access: WorkspaceAccess) -> None:
    """A member leaves the workspace by themselves (all their roles go).
    The owner cannot leave: they archive or delete the workspace."""
    user = access.user
    if user is None or not access.is_member:
        raise AppError(404, "member_not_found", "You are not a member of this workspace")
    await db.execute(
        delete(Membership).where(
            Membership.workspace_id == access.workspace.id, Membership.user_id == user.id
        )
    )
    activity.record(
        db,
        "member_removed",
        actor=user,
        workspace_id=access.workspace.id,
        target_type="user",
        target_id=user.id,
        target_label=user.username,
        details={"left": True},
    )
    await db.commit()


async def _check_role_change(
    db: AsyncSession, access: WorkspaceAccess, user_id: int, role: str
) -> tuple[User, set[str]]:
    if role not in ROLE_GRANTERS:
        raise AppError(
            400, "role_not_grantable", "Only editor and reviewer can be granted or removed"
        )
    if not access.can_manage_role(role):
        raise forbidden(f"Only the {ROLE_GRANTERS[role]} can grant or remove {role}")
    require_not_archived(access)
    user = await db.get(User, user_id)
    roles = await _roles_of(db, access.workspace.id, user_id)
    if user is None or MEMBER not in roles:
        raise member_not_found(user_id)
    return user, roles


async def grant_role(db: AsyncSession, access: WorkspaceAccess, user_id: int, role: str) -> Member:
    user, roles = await _check_role_change(db, access, user_id, role)
    if role in roles:
        raise AppError(409, "role_already_granted", f"{user.username} already has {role}")
    db.add(
        Membership(
            workspace_id=access.workspace.id, user_id=user_id, role_id=await _role_id(db, role)
        )
    )
    _event(db, "role_added", access, user, role)
    await db.commit()
    return Member(user=user, roles=sorted(roles | {role}))


async def revoke_role(db: AsyncSession, access: WorkspaceAccess, user_id: int, role: str) -> Member:
    user, roles = await _check_role_change(db, access, user_id, role)
    if role not in roles:
        raise AppError(404, "role_not_granted", f"{user.username} does not have {role}")
    await db.execute(
        delete(Membership).where(
            Membership.workspace_id == access.workspace.id,
            Membership.user_id == user_id,
            Membership.role_id == await _role_id(db, role),
        )
    )
    _event(db, "role_removed", access, user, role)
    await db.commit()
    return Member(user=user, roles=sorted(roles - {role}))
