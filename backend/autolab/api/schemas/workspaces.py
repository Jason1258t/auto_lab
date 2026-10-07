"""Request and response bodies for workspaces, members and activity."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autolab.db.models.enums import WorkspaceVisibility


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    visibility: WorkspaceVisibility
    owner_id: int | None
    # Filled by the router (one extra query for a whole list).
    owner_username: str | None = None
    owner_display_name: str | None = None
    archived_at: datetime | None
    created_at: datetime
    # The caller's place in this workspace (empty when not logged in).
    is_owner: bool = False
    my_roles: list[str] = []


class MemberIn(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=320)


class MemberOut(BaseModel):
    user_id: int
    username: str
    display_name: str
    roles: list[str]


class ActivityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_id: int | None
    actor_name: str | None
    action: str
    target_type: str | None
    target_id: int | None
    target_label: str | None
    details: dict[str, Any] | None
