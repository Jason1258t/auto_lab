"""Group 4: results and evidence."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk, created_at, pg_enum
from autolab.db.models.enums import ReviewResult, SourceKind


class Work(Base):
    """A task produces one work. Title = tasks.title."""

    __tablename__ = "works"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkSource(Base):
    """One source used in one work. The full text is not stored."""

    __tablename__ = "work_sources"

    id: Mapped[int] = bigint_pk()
    work_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("works.task_id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[SourceKind] = mapped_column(pg_enum(SourceKind, "source_kind"))
    location: Mapped[str] = mapped_column(Text)  # URL, or file name with part of its path
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("work_id", "location"),)


class Quote(Base):
    """Claim and exact quote in one row. A claim with two sources = two
    rows."""

    __tablename__ = "quotes"

    id: Mapped[int] = bigint_pk()
    work_source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("work_sources.id", ondelete="CASCADE"), index=True
    )
    claim: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    placement: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class TaskReview(Base):
    __tablename__ = "task_reviews"

    id: Mapped[int] = bigint_pk()
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    result: Mapped[ReviewResult] = mapped_column(pg_enum(ReviewResult, "review_result"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        # A rejection needs a comment: it is the input for the revise steps.
        CheckConstraint("result = 'accepted' OR comment IS NOT NULL", name="task_reviews_check"),
    )


class Publisher(Base):
    """A public signature for publications. Does not show the workspace."""

    __tablename__ = "publishers"

    id: Mapped[int] = bigint_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = bigint_pk()
    # RESTRICT: a published work protects its task.
    work_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("works.task_id", ondelete="RESTRICT"), unique=True
    )
    publisher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("publishers.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("publications_publisher_published_idx", "publisher_id", text("published_at DESC")),
    )
