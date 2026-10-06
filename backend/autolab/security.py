"""Passwords and tokens. No database access here."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"

# Login checks a hash even when the email is unknown, so the answer takes
# the same time and does not show which emails exist.
DUMMY_PASSWORD_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# --- Access token: short JWT, not stored in the DB ---


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    session_id: int


def create_access_token(user_id: int, session_id: int, secret: str, minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> AccessClaims | None:
    """Return the claims, or None if the token is broken or expired."""
    try:
        data = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "sid", "exp"]}
        )
        return AccessClaims(user_id=int(data["sub"]), session_id=int(data["sid"]))
    except (jwt.PyJWTError, ValueError):
        return None


# --- Refresh token: "<session_id>.<random secret>" ---
# Only a hash of the secret is stored (sessions.refresh_token_hash). The
# session id in front lets us find the row, and see when an old, already
# replaced secret is used again.


def new_refresh_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_secret(secret: str) -> str:
    # sha256 is enough here: the secret is 32 random bytes, not a password.
    return hashlib.sha256(secret.encode()).hexdigest()


def make_refresh_token(session_id: int, secret: str) -> str:
    return f"{session_id}.{secret}"


def parse_refresh_token(token: str) -> tuple[int, str] | None:
    session_id, dot, secret = token.partition(".")
    if not dot or not session_id.isdigit() or not secret:
        return None
    return int(session_id), secret
