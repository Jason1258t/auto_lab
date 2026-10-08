"""Catalog (models, pipelines) and admin routes."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.services.admins import grant_admin
from tests.conftest import Catalog

API = "/api/v1"


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


async def test_catalog_is_public(client: httpx.AsyncClient, catalog: Catalog) -> None:
    models = await client.get(f"{API}/models")
    assert [m["name"] for m in models.json()] == ["test-model"]

    pipelines = {p["name"]: p for p in (await client.get(f"{API}/pipelines")).json()}
    assert pipelines["research"]["version_name"] == "1.0.0"
    assert pipelines["study_notes"]["version_name"] is None  # no version file yet


async def test_admin_manages_models(client: httpx.AsyncClient, make_user, db: AsyncSession) -> None:
    root, ann = await make_user("root"), await make_user("ann")
    await grant_admin(db, root.id, granted_by="test")

    body = {"provider_id": 1, "name": "llama3.1:8b", "context_length": 8192, "vram_mb": 4800}
    assert (
        await client.post(f"{API}/admin/models", json=body, headers=ann.headers)
    ).status_code == 403
    created = await client.post(f"{API}/admin/models", json=body, headers=root.headers)
    assert created.status_code == 201
    again = await client.post(f"{API}/admin/models", json=body, headers=root.headers)
    assert code(again) == "model_exists"

    # Models are never deleted, only marked unavailable.
    model_id = created.json()["id"]
    hidden = await client.patch(
        f"{API}/admin/models/{model_id}", json={"available": False}, headers=root.headers
    )
    assert hidden.json()["available"] is False
    assert (await client.get(f"{API}/models")).json() == []

    # Token budget profile (migration 0008): 'small' by default.
    assert created.json()["size_class"] == "small"
    thinking = await client.patch(
        f"{API}/admin/models/{model_id}",
        json={"size_class": "medium_think", "reasoning_tokens": 2048},
        headers=root.headers,
    )
    assert (thinking.json()["size_class"], thinking.json()["reasoning_tokens"]) == (
        "medium_think",
        2048,
    )
    wrong = await client.patch(
        f"{API}/admin/models/{model_id}", json={"size_class": "huge"}, headers=root.headers
    )
    assert wrong.status_code == 422


async def test_admin_manages_providers(
    client: httpx.AsyncClient, make_user, db: AsyncSession
) -> None:
    root = await make_user("root")
    await grant_admin(db, root.id, granted_by="test")

    body = {"name": "openrouter", "adapter": "openai_compatible", "secret_id": "openrouter-key"}
    created = await client.post(f"{API}/admin/model-providers", json=body, headers=root.headers)
    assert created.status_code == 201
    assert "secret_id" not in created.json()
    bad = await client.post(
        f"{API}/admin/model-providers", json={"name": "x", "adapter": "magic"}, headers=root.headers
    )
    assert bad.status_code == 422


async def test_admins_grant_and_revoke(
    client: httpx.AsyncClient, make_user, db: AsyncSession
) -> None:
    root, ann = await make_user("root"), await make_user("ann")
    await grant_admin(db, root.id, granted_by="test")

    assert (
        await client.post(f"{API}/admin/admins/{ann.id}", headers=root.headers)
    ).status_code == 201
    me = await client.get(f"{API}/me", headers=ann.headers)
    assert me.json()["is_admin"] is True

    self_revoke = await client.delete(f"{API}/admin/admins/{root.id}", headers=root.headers)
    assert code(self_revoke) == "cannot_revoke_self"
    assert (
        await client.delete(f"{API}/admin/admins/{ann.id}", headers=root.headers)
    ).status_code == 204

    log = await client.get(f"{API}/admin/activity", headers=root.headers)
    assert [e["action"] for e in log.json()] == ["admin_revoked", "admin_granted", "admin_granted"]
