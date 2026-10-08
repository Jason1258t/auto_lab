"""Plain data the engine gets from its caller (no database rows)."""

from dataclasses import dataclass

from autolab_engine.enums import ModelSizeClass


@dataclass(frozen=True)
class TaskInput:
    id: int | str  # for logs only
    title: str
    input: str


@dataclass(frozen=True)
class ModelInfo:
    """What the engine needs to know about the model of a task."""

    name: str
    context_length: int
    size_class: ModelSizeClass = ModelSizeClass.SMALL
    reasoning_tokens: int | None = None  # *_think classes; None = default
    max_output_tokens: int | None = None  # the model's own cap; None = none
