"""Group 1: people and access."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, SmallInteger, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk, created_at, pg_enum, smallint_pk
from autolab.db.models.enums import WorkspaceVisibility


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = bigint_pk()
    email: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        # Emails are compared without case.
        Index("users_email_lower_key", func.lower(email), unique=True),
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = bigint_pk()
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Creator never changes. owner_id NULL = free project, or the owner's
    # account was deleted.
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Public once, public forever: a DB trigger blocks public -> private.
    visibility: Mapped[WorkspaceVisibility] = mapped_column(
        pg_enum(WorkspaceVisibility, "workspace_visibility"),
        server_default=text("'private'"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = smallint_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class Membership(Base):
    """A person can have many roles in one workspace. The owner is
    `workspaces.owner_id`, not a row here."""

    __tablename__ = "memberships"

    workspace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True
    )
