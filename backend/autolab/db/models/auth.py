"""Group 6: auth."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk, created_at, smallint_pk


class PasswordCredential(Base):
    """Login uses users.email."""

    __tablename__ = "password_credentials"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text)  # argon2, never the password
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthProvider(Base):
    """External login providers. Built later."""

    __tablename__ = "auth_providers"

    id: Mapped[int] = smallint_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    enabled: Mapped[bool] = mapped_column(server_default=text("false"))


class UserIdentity(Base):
    __tablename__ = "user_identities"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("auth_providers.id", ondelete="RESTRICT")
    )
    provider_user_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (UniqueConstraint("provider_id", "provider_user_id"),)


class Admin(Base):
    """A row here = an admin."""

    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    granted_by: Mapped[str | None] = mapped_column(Text)  # plain text for now


class AuthSession(Base):
    """Refresh tokens, stored only as a hash. Access tokens are short JWTs
    and are not stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("expires_at > created_at", name="sessions_check"),)
