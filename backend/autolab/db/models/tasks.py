"""Group 3: tasks, pipelines and LLM calls."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk, created_at, pg_enum, smallint_pk
from autolab.db.models.enums import FinishReason, LlmCallStatus, TaskStatus, TaskStepStatus


class Pipeline(Base):
    """A pipeline is the task type (research, study_notes, ...)."""

    __tablename__ = "pipelines"

    id: Mapped[int] = smallint_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class PipelineVersion(Base):
    """One row = one fixed snapshot of a pipeline YAML file."""

    __tablename__ = "pipeline_versions"

    id: Mapped[int] = bigint_pk()
    pipeline_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("pipelines.id", ondelete="RESTRICT")
    )
    version_name: Mapped[str] = mapped_column(Text)  # '1.0.1', for people
    version_code: Mapped[int]  # for sorting; newest = MAX
    file_path: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(Text)  # sha256
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("pipeline_id", "version_code"),
        UniqueConstraint("pipeline_id", "version_name"),
        CheckConstraint("version_code > 0", name="pipeline_versions_version_code_check"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = bigint_pk()
    # RESTRICT: only an empty workspace can be deleted.
    workspace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    pipeline_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pipeline_versions.id", ondelete="RESTRICT")
    )
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("models.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(Text)
    input: Mapped[str] = mapped_column(Text)
    # 'done' <=> an accepted row in task_reviews (kept in sync by services).
    status: Mapped[TaskStatus] = mapped_column(
        pg_enum(TaskStatus, "task_status"), server_default=text("'draft'")
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("tasks_workspace_created_idx", "workspace_id", text("created_at DESC")),
        # Partial indexes: the worker looks for work, a reviewer looks for
        # tasks to review.
        Index(
            "tasks_active_status_idx",
            "status",
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index(
            "tasks_in_review_reviewer_idx",
            "reviewer_id",
            postgresql_where=text("status = 'in_review'"),
        ),
    )


class TaskStep(Base):
    __tablename__ = "task_steps"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    step_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # A cancelled task puts its running step back to 'pending'.
    status: Mapped[TaskStepStatus] = mapped_column(
        pg_enum(TaskStepStatus, "task_step_status"), server_default=text("'pending'")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    # NULL = normal step; set = extra revise step caused by this review.
    review_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("task_reviews.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("step_index >= 0", name="task_steps_step_index_check"),)


class LlmCall(Base):
    """One row = one request to a model. id is also the key in the log
    store, where the full prompt and output live."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = bigint_pk()
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    step_index: Mapped[int] = mapped_column(SmallInteger)
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("models.id", ondelete="RESTRICT"))
    attempt: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    # 'done' <=> a row in llm_responses (kept in sync by the worker).
    status: Mapped[LlmCallStatus] = mapped_column(
        pg_enum(LlmCallStatus, "llm_call_status"), server_default=text("'queued'")
    )
    response_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)  # short, safe for users
    created_at: Mapped[datetime] = created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "step_index"],
            ["task_steps.task_id", "task_steps.step_index"],
            ondelete="CASCADE",
        ),
        CheckConstraint("attempt >= 1", name="llm_calls_attempt_check"),
        Index("llm_calls_task_step_idx", "task_id", "step_index"),
    )


class LlmResponse(Base):
    """0 or 1 response per call. Cost is not stored: tokens x model price."""

    __tablename__ = "llm_responses"

    call_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("llm_calls.id", ondelete="CASCADE"), primary_key=True
    )
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    finish_reason: Mapped[FinishReason | None] = mapped_column(
        pg_enum(FinishReason, "finish_reason")
    )
    valid_json: Mapped[bool | None]  # NULL = no schema
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="llm_responses_input_tokens_check"),
        CheckConstraint("output_tokens >= 0", name="llm_responses_output_tokens_check"),
    )


class LogDeletion(Base):
    """Outbox for the log cleanup worker. Filled by a DB trigger when an
    llm_calls row is deleted. No FK: the call row is already gone."""

    __tablename__ = "log_deletions"

    call_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = created_at()
