"""pipeline upload activity

activity_events: action 'pipeline_uploaded', target 'pipeline' (an admin
uploads a pipeline version in the admin page). Written by hand: the
CHECK lists are not seen by autogenerate.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
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
    "unarchived",
    "workspace_deleted",
    "file_added",
    "file_removed",
)
NEW_ACTIONS = (*OLD_ACTIONS, "pipeline_uploaded")
OLD_TARGETS = (
    "workspace",
    "membership",
    "task",
    "work",
    "publication",
    "publisher",
    "user",
    "file",
)
NEW_TARGETS = (*OLD_TARGETS, "pipeline")


def in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def set_checks(actions: tuple[str, ...], targets: tuple[str, ...]) -> None:
    for name, column, values in (
        ("activity_events_action_check", "action", actions),
        ("activity_events_target_type_check", "target_type", targets),
    ):
        op.drop_constraint(name, "activity_events", type_="check")
        op.create_check_constraint(name, "activity_events", f"{column} IN ({in_list(values)})")


def upgrade() -> None:
    """Upgrade schema."""
    set_checks(NEW_ACTIONS, NEW_TARGETS)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM activity_events WHERE action = 'pipeline_uploaded'")
    set_checks(OLD_ACTIONS, OLD_TARGETS)
