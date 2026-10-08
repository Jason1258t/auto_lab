"""Fixed lists the engine shares with AutoLab's database.

The PostgreSQL ENUM types finish_reason and model_size_class have the
same values; the backend imports these classes, so there is one list.
"""

from enum import StrEnum


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    OTHER = "other"


class ModelSizeClass(StrEnum):
    """How big a step a model handles; *_think = a thinking model of that
    size, it gets models.reasoning_tokens of extra room (migration 0008)."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    SMALL_THINK = "small_think"
    MEDIUM_THINK = "medium_think"
    LARGE_THINK = "large_think"

    @property
    def thinks(self) -> bool:
        return self.value.endswith("_think")
