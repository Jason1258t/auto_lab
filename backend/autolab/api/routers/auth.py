"""Sign-up, login, refresh, logout."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from autolab.api.deps import CurrentPrincipal, DbSession, SettingsDep
from autolab.api.schemas.auth import LoginIn, SignupIn, TokenOut, UserOut
from autolab.config import Settings
from autolab.errors import AppError
from autolab.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# The browser sends the cookie only to the auth routes.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,  # JavaScript cannot read it
        secure=settings.cookie_secure,  # HTTPS only (see config.py)
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def token_out(response: Response, settings: Settings, tokens: auth_service.Tokens) -> TokenOut:
    set_refresh_cookie(response, settings, tokens.refresh_token)
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignupIn, db: DbSession) -> UserOut:
    user = await auth_service.signup(
        db,
        email=body.email,
        username=body.username,
        display_name=body.display_name,
        password=body.password,
    )
    return UserOut.model_validate(user)


@router.post("/login")
async def login(
    body: LoginIn, response: Response, db: DbSession, settings: SettingsDep
) -> TokenOut:
    tokens = await auth_service.login(db, settings, email=body.email, password=body.password)
    return token_out(response, settings, tokens)


@router.post("/refresh")
async def refresh(
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenOut:
    if refresh_token is None:
        raise AppError(401, "invalid_refresh_token", "Please log in again")
    tokens = await auth_service.refresh(db, settings, refresh_token)
    return token_out(response, settings, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(principal: CurrentPrincipal, response: Response, db: DbSession) -> None:
    await auth_service.logout(db, principal.session_id)
    clear_refresh_cookie(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(principal: CurrentPrincipal, response: Response, db: DbSession) -> None:
    await auth_service.logout_all(db, principal.user.id)
    clear_refresh_cookie(response)
