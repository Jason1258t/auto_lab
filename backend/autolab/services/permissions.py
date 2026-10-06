"""All access rules for a workspace, in one place. Routers and services
ask these questions; they never check roles themselves.

Roles (Discord-like): every person in a workspace has the base role
'member'. 'editor' and 'reviewer' are extra. The owner is
workspaces.owner_id, not a role.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Membership, Role, User, Workspace
from autolab.db.models.enums import WorkspaceVisibility
from autolab.errors import AppError
from autolab.services.admins import is_admin

MEMBER = "member"
EDITOR = "editor"
REVIEWER = "reviewer"

# Who may grant or remove each extra role.
ROLE_GRANTERS = {
    EDITOR: "owner",
    REVIEWER: "owner or editor",
}


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    user: User | None  # None = not logged in
    is_owner: bool
    roles: frozenset[str]
    is_admin: bool

    @property
    def is_member(self) -> bool:
        return MEMBER in self.roles

    @property
    def is_archived(self) -> bool:
        return self.workspace.archived_at is not None

    @property
    def can_see(self) -> bool:
        """Name, description and works. Public: anyone. Private: owner,
        members, admins (admins only by a direct link)."""
        return self.workspace.visibility == WorkspaceVisibility.PUBLIC or self.can_see_inside

    @property
    def can_see_inside(self) -> bool:
        """Members, tasks, steps, reviews, LLM calls (also in a public
        workspace)."""
        return self.is_owner or self.is_member or self.is_admin

    @property
    def can_read_activity(self) -> bool:
        return self.is_owner or EDITOR in self.roles or self.is_admin

    @property
    def can_edit_tasks(self) -> bool:
        """Create, edit, queue, cancel, delete tasks; change the reviewer."""
        return self.is_owner or EDITOR in self.roles

    @property
    def can_edit_files(self) -> bool:
        """Add and remove workspace files."""
        return self.is_owner or EDITOR in self.roles

    def can_manage_role(self, role: str) -> bool:
        if role == EDITOR:
            return self.is_owner
        if role == REVIEWER:
            return self.is_owner or EDITOR in self.roles
        return False


def can_review(access: WorkspaceAccess, reviewer_id: int | None) -> bool:
    """The assigned reviewer, the owner, or any member with the editor or
    reviewer role (backend_spec.md, section 6)."""
    if access.user is None:
        return False
    return (
        access.user.id == reviewer_id
        or access.is_owner
        or EDITOR in access.roles
        or REVIEWER in access.roles
    )


def workspace_not_found(workspace_id: int) -> AppError:
    return AppError(404, "workspace_not_found", f"Workspace {workspace_id} not found")


def forbidden(message: str) -> AppError:
    return AppError(403, "forbidden", message)


async def load_access(db: AsyncSession, workspace_id: int, user: User | None) -> WorkspaceAccess:
    """Load a workspace with the user's rights in it. Raises 404 if the
    user may not see it: the API does not show that a private workspace
    exists."""
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise workspace_not_found(workspace_id)

    roles: frozenset[str] = frozenset()
    admin = False
    if user is not None:
        names = await db.scalars(
            select(Role.name)
            .join(Membership, Membership.role_id == Role.id)
            .where(Membership.workspace_id == workspace_id, Membership.user_id == user.id)
        )
        roles = frozenset(names)
        admin = await is_admin(db, user.id)

    access = WorkspaceAccess(
        workspace=workspace,
        user=user,
        is_owner=user is not None and workspace.owner_id == user.id,
        roles=roles,
        is_admin=admin,
    )
    if not access.can_see:
        raise workspace_not_found(workspace_id)
    return access


def require_owner(access: WorkspaceAccess) -> User:
    if not access.is_owner or access.user is None:
        raise forbidden("Only the owner can do this")
    return access.user


def require_inside(access: WorkspaceAccess) -> None:
    if not access.can_see_inside:
        raise forbidden("Only members can see this")


def require_task_editor(access: WorkspaceAccess) -> None:
    if not access.can_edit_tasks:
        raise forbidden("Only the owner and editors can change tasks")


def require_not_archived(access: WorkspaceAccess) -> None:
    if access.is_archived:
        raise AppError(409, "workspace_archived", "The workspace is archived (read-only)")
