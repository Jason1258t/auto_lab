"""member role and more activity actions

- Role 'viewer' becomes 'member': the base role every person in a
  workspace has (like @everyone in Discord). Same id, so existing rows
  keep working.
- activity_events.action: add 'unarchived' and 'workspace_deleted'.

Written by hand: autogenerate does not see data or CHECK changes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 23:33:45.041064

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIONS = (
    "member_added",
    "member_removed",
    "role_added",
    "role_removed",
    "workspace_taken",
    "made_public",
    "archived",
    "task_deleted",
    "work_published",
    "publisher_created",
    "admin_granted",
    "admin_revoked",
    "user_deleted",
)
NEW_ACTIONS = OLD_ACTIONS + ("unarchived", "workspace_deleted")


def set_action_check(actions: tuple[str, ...]) -> None:
    values = ", ".join(f"'{a}'" for a in actions)
    op.drop_constraint("activity_events_action_check", "activity_events", type_="check")
    op.create_check_constraint(
        "activity_events_action_check", "activity_events", f"action IN ({values})"
    )


def upgrade() -> None:
    op.execute(
        "UPDATE roles SET name = 'member', description = 'Is in the workspace; can read' "
        "WHERE name = 'viewer'"
    )
    set_action_check(NEW_ACTIONS)


def downgrade() -> None:
    # Fails if events with the new actions exist: delete them first.
    set_action_check(OLD_ACTIONS)
    op.execute(
        "UPDATE roles SET name = 'viewer', description = 'Can only read' WHERE name = 'member'"
    )
