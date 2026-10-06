"""Auth flow through the HTTP API, and create-admin."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import ActivityEvent, Admin, AuthSession
from autolab.errors import AppError
from autolab.services.admins import grant_admin

API = "/api/v1"
ANN = {
    "email": "ann@example.com",
    "username": "ann",
    "display_name": "Ann",
    "password": "correct horse battery",
}


async def signup(client: httpx.AsyncClient, **changes: str) -> httpx.Response:
    return await client.post(f"{API}/auth/signup", json={**ANN, **changes})


async def login(client: httpx.AsyncClient, password: str = ANN["password"]) -> httpx.Response:
    return await client.post(
        f"{API}/auth/login", json={"email": ANN["email"], "password": password}
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def refresh_with(client: httpx.AsyncClient, refresh_token: str) -> httpx.Response:
    client.cookies.clear()
    return await client.post(
        f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={refresh_token}"}
    )


async def test_signup(client: httpx.AsyncClient) -> None:
    response = await signup(client)
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "ann"
    assert "password" not in body
    assert "password_hash" not in body


async def test_signup_conflicts(client: httpx.AsyncClient) -> None:
    await signup(client)

    same_email_other_case = await signup(client, email="ANN@example.com", username="ann2")
    assert same_email_other_case.status_code == 409
    assert same_email_other_case.json()["error"]["code"] == "email_taken"

    same_username = await signup(client, email="other@example.com")
    assert same_username.status_code == 409
    assert same_username.json()["error"]["code"] == "username_taken"


async def test_signup_validation(client: httpx.AsyncClient) -> None:
    response = await signup(client, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_login_and_me(client: httpx.AsyncClient) -> None:
    await signup(client)

    wrong = await login(client, password="wrong password")
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"

    response = await login(client)
    assert response.status_code == 200
    assert "refresh_token" in response.cookies
    token = response.json()["access_token"]

    me = await client.get(f"{API}/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["username"] == "ann"
    assert me.json()["is_admin"] is False

    renamed = await client.patch(
        f"{API}/me", headers=bearer(token), json={"display_name": "Ann B."}
    )
    assert renamed.json()["display_name"] == "Ann B."


async def test_me_needs_login(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{API}/me")).status_code == 401
    bad = await client.get(f"{API}/me", headers=bearer("not-a-token"))
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "not_authenticated"


async def test_refresh_rotates_token(client: httpx.AsyncClient) -> None:
    await signup(client)
    first = (await login(client)).cookies["refresh_token"]

    response = await refresh_with(client, first)
    assert response.status_code == 200
    second = response.cookies["refresh_token"]
    assert second != first
    assert (
        await client.get(f"{API}/me", headers=bearer(response.json()["access_token"]))
    ).is_success


async def test_refresh_moves_expiry_forward(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await signup(client)
    token = (await login(client)).cookies["refresh_token"]
    session = await db.scalar(select(AuthSession))
    # Pretend the session was created long ago and expires tomorrow.
    session.expires_at = datetime.now(UTC) + timedelta(days=1)
    await db.commit()

    assert (await refresh_with(client, token)).status_code == 200
    await db.refresh(session)
    assert session.expires_at > datetime.now(UTC) + timedelta(days=29)


async def test_reused_refresh_token_ends_session(client: httpx.AsyncClient) -> None:
    await signup(client)
    first = (await login(client)).cookies["refresh_token"]
    second = (await refresh_with(client, first)).cookies["refresh_token"]

    # The old token is used again: maybe stolen. The whole session ends,
    # so even the newest token stops working.
    assert (await refresh_with(client, first)).status_code == 401
    assert (await refresh_with(client, second)).status_code == 401


async def test_logout(client: httpx.AsyncClient) -> None:
    await signup(client)
    response = await login(client)
    refresh_token = response.cookies["refresh_token"]

    logout = await client.post(
        f"{API}/auth/logout", headers=bearer(response.json()["access_token"])
    )
    assert logout.status_code == 204
    assert (await refresh_with(client, refresh_token)).status_code == 401


async def test_logout_all(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await signup(client)
    first = await login(client)
    await login(client)

    await client.post(f"{API}/auth/logout-all", headers=bearer(first.json()["access_token"]))
    sessions = (await db.scalars(select(AuthSession))).all()
    assert len(sessions) == 2
    assert all(s.revoked_at is not None for s in sessions)


async def test_grant_admin(client: httpx.AsyncClient, db: AsyncSession) -> None:
    user_id = (await signup(client)).json()["id"]

    await grant_admin(db, user_id, granted_by="cli")
    assert await db.get(Admin, user_id) is not None

    event = await db.scalar(select(ActivityEvent).where(ActivityEvent.action == "admin_granted"))
    assert event is not None
    assert event.target_id == user_id
    assert event.target_label == "ann"
    assert event.actor_id is None  # the system (CLI)

    with pytest.raises(AppError) as again:
        await grant_admin(db, user_id, granted_by="cli")
    assert again.value.code == "already_admin"

    with pytest.raises(AppError) as missing:
        await grant_admin(db, 999_999, granted_by="cli")
    assert missing.value.code == "user_not_found"
