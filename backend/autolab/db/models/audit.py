"""Group 5: audit and logging."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk

# text + CHECK, not enums: these lists grow with every new feature.
ACTIONS = (
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
TARGET_TYPES = (
    "workspace",
    "membership",
    "task",
    "work",
    "publication",
    "publisher",
    "user",
    "file",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ActivityEvent(Base):
    """Important human actions. No FKs: rows must survive deletes. Names
    are copied, so the log still reads well later."""

    __tablename__ = "activity_events"

    id: Mapped[int] = bigint_pk()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_id: Mapped[int | None] = mapped_column(BigInteger)  # NULL = the system
    actor_name: Mapped[str | None] = mapped_column(Text)
    workspace_id: Mapped[int | None] = mapped_column(BigInteger)  # NULL = global action
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    target_label: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(_in_list("action", ACTIONS), name="activity_events_action_check"),
        CheckConstraint(
            _in_list("target_type", TARGET_TYPES), name="activity_events_target_type_check"
        ),
        Index(
            "activity_events_workspace_occurred_idx",
            "workspace_id",
            text("occurred_at DESC"),
        ),
    )
