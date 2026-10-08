"""Python versions of the PostgreSQL ENUM types (fixed lists)."""

from enum import StrEnum

# Shared with the pipeline engine (same values as the DB types).
from autolab_engine.enums import FinishReason, ModelSizeClass

__all__ = [
    "CapabilityKind",
    "FinishReason",
    "LlmCallStatus",
    "ModelSizeClass",
    "ReviewResult",
    "SourceKind",
    "TaskStatus",
    "TaskStepStatus",
    "WorkspaceVisibility",
]


class WorkspaceVisibility(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


class CapabilityKind(StrEnum):
    STRENGTH = "strength"
    WEAKNESS = "weakness"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"  # a step failed; final, like cancelled (migration 0003)


class TaskStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


class LlmCallStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceKind(StrEnum):
    WEB = "web"
    FILE = "file"


class ReviewResult(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
