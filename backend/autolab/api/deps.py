"""Shared FastAPI dependencies: DB session, settings, current user."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings, get_settings
from autolab.db.models import User
from autolab.errors import AppError
from autolab.security import decode_access_token
from autolab.services.admins import is_admin


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One DB session per request. Services commit; anything not committed
    is rolled back when the session closes."""
    async with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """The logged-in user and the session their access token belongs to."""

    user: User
    session_id: int


async def get_principal(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    claims = (
        decode_access_token(credentials.credentials, settings.jwt_secret) if credentials else None
    )
    user = await db.get(User, claims.user_id) if claims else None
    if claims is None or user is None:
        raise AppError(401, "not_authenticated", "Please log in")
    return Principal(user=user, session_id=claims.session_id)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def get_optional_user(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """For routes that also work without login (public workspaces). No
    token = None; a broken or expired token is still an error."""
    if credentials is None:
        return None
    return (await get_principal(db, settings, credentials)).user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_admin(principal: CurrentPrincipal, db: DbSession) -> Principal:
    if not await is_admin(db, principal.user.id):
        raise AppError(403, "forbidden", "Admins only")
    return principal


AdminPrincipal = Annotated[Principal, Depends(get_admin)]
