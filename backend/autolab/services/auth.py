"""Sign-up, login, refresh and logout. Each function is one transaction
and commits at the end."""

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import AuthSession, PasswordCredential, User
from autolab.errors import AppError
from autolab.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    hash_refresh_secret,
    make_refresh_token,
    new_refresh_secret,
    parse_refresh_token,
    verify_password,
)

# Which unique constraint failed -> what to tell the client.
SIGNUP_CONFLICTS = {
    "users_email_lower_key": ("email_taken", "This email is already registered"),
    "users_username_key": ("username_taken", "This username is already taken"),
}


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int  # access token lifetime, seconds


def invalid_refresh() -> AppError:
    return AppError(401, "invalid_refresh_token", "Please log in again")


async def signup(
    db: AsyncSession, *, email: str, username: str, display_name: str, password: str
) -> User:
    # Hash before the transaction starts: argon2 is slow on purpose, and it
    # runs in a thread so it does not block other requests.
    password_hash = await asyncio.to_thread(hash_password, password)

    user = User(email=email, username=username, display_name=display_name)
    db.add(user)
    try:
        await db.flush()  # gets user.id; unique constraints are checked here
    except IntegrityError as exc:
        await db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint in SIGNUP_CONFLICTS:
            code, message = SIGNUP_CONFLICTS[constraint]
            raise AppError(409, code, message) from exc
        raise

    db.add(PasswordCredential(user_id=user.id, password_hash=password_hash))
    await db.commit()
    return user


async def _start_session(db: AsyncSession, settings: Settings, user_id: int) -> Tokens:
    secret = new_refresh_secret()
    session = AuthSession(
        user_id=user_id,
        refresh_token_hash=hash_refresh_secret(secret),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    await db.flush()
    await db.commit()
    return _tokens(settings, user_id, session.id, secret)


def _tokens(settings: Settings, user_id: int, session_id: int, secret: str) -> Tokens:
    return Tokens(
        access_token=create_access_token(
            user_id, session_id, settings.jwt_secret, settings.access_token_minutes
        ),
        refresh_token=make_refresh_token(session_id, secret),
        expires_in=settings.access_token_minutes * 60,
    )


async def login(db: AsyncSession, settings: Settings, *, email: str, password: str) -> Tokens:
    user = await db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    credential = await db.get(PasswordCredential, user.id) if user else None
    password_hash = credential.password_hash if credential else DUMMY_PASSWORD_HASH
    ok = await asyncio.to_thread(verify_password, password_hash, password)
    if user is None or credential is None or not ok:
        # Same answer for "no such email" and "wrong password".
        raise AppError(401, "invalid_credentials", "Wrong email or password")
    return await _start_session(db, settings, user.id)


async def refresh(db: AsyncSession, settings: Settings, refresh_token: str) -> Tokens:
    """Give a new access + refresh token pair (rotation). The session's
    expiry moves forward too (sliding window): a user who comes back at
    least once in REFRESH_TOKEN_DAYS never has to log in again."""
    parsed = parse_refresh_token(refresh_token)
    if parsed is None:
        raise invalid_refresh()
    session_id, secret = parsed

    # FOR UPDATE: two refreshes with the same token cannot both win.
    session = await db.scalar(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise invalid_refresh()

    if not secrets.compare_digest(session.refresh_token_hash, hash_refresh_secret(secret)):
        # An old token of this session was used again. It may be stolen,
        # so end the whole session.
        session.revoked_at = now
        await db.commit()
        raise invalid_refresh()

    new_secret = new_refresh_secret()
    session.refresh_token_hash = hash_refresh_secret(new_secret)
    session.last_used_at = now
    session.expires_at = now + timedelta(days=settings.refresh_token_days)
    await db.commit()
    return _tokens(settings, session.user_id, session.id, new_secret)


async def logout(db: AsyncSession, session_id: int) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await db.commit()


async def logout_all(db: AsyncSession, user_id: int) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await db.commit()
