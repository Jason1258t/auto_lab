"""Writes activity_events rows. The caller commits, so the action and its
event are saved together or not at all."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import ActivityEvent, User


def record(
    db: AsyncSession,
    action: str,
    *,
    actor: User | None = None,
    workspace_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    target_label: str | None = None,
    details: dict[str, Any] | None = None,
) -> ActivityEvent:
    """actor None = the system (for example a CLI command)."""
    event = ActivityEvent(
        action=action,
        actor_id=actor.id if actor else None,
        actor_name=actor.username if actor else None,
        workspace_id=workspace_id,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details,
    )
    db.add(event)
    return event
