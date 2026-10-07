"""Workspaces, members, roles and activity: one test per rule of the
permission table in drafts/backend_spec.md."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Model, Pipeline, PipelineVersion, Task
from autolab.services.admins import grant_admin
from tests.conftest import ApiUser

W = "/api/v1/workspaces"


async def create(client: httpx.AsyncClient, owner: ApiUser, name: str = "Lab") -> int:
    response = await client.post(W, json={"name": name}, headers=owner.headers)
    assert response.status_code == 201
    return response.json()["id"]


async def add(client: httpx.AsyncClient, ws: int, by: ApiUser, who: str) -> httpx.Response:
    return await client.post(
        f"{W}/{ws}/members", json={"username_or_email": who}, headers=by.headers
    )


async def grant(
    client: httpx.AsyncClient, ws: int, by: ApiUser, user: ApiUser, role: str
) -> httpx.Response:
    return await client.put(f"{W}/{ws}/members/{user.id}/roles/{role}", headers=by.headers)


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


async def test_private_workspace_is_hidden(client: httpx.AsyncClient, make_user) -> None:
    ann, bob = await make_user("ann"), await make_user("bob")
    ws = await create(client, ann)

    mine = await client.get(f"{W}/{ws}", headers=ann.headers)
    assert mine.json()["is_owner"] is True
    assert mine.json()["visibility"] == "private"

    # 404, not 403: the API does not show that the workspace exists.
    assert (await client.get(f"{W}/{ws}")).status_code == 404
    assert (await client.get(f"{W}/{ws}", headers=bob.headers)).status_code == 404


async def test_public_workspace(client: httpx.AsyncClient, make_user) -> None:
    ann = await make_user("ann")
    ws = await create(client, ann)

    assert (await client.post(f"{W}/{ws}/make-public", headers=ann.headers)).status_code == 200
    again = await client.post(f"{W}/{ws}/make-public", headers=ann.headers)
    assert code(again) == "already_public"

    # Anyone sees it, without login...
    assert (await client.get(f"{W}/{ws}")).status_code == 200
    assert [w["id"] for w in (await client.get(W, params={"scope": "public"})).json()] == [ws]
    # ...but not what is inside.
    assert (await client.get(f"{W}/{ws}/members")).status_code == 403


async def test_only_owner_edits(client: httpx.AsyncClient, make_user) -> None:
    ann, bob = await make_user("ann"), await make_user("bob")
    ws = await create(client, ann)
    await add(client, ws, ann, "bob")

    renamed = await client.patch(f"{W}/{ws}", json={"name": "New"}, headers=ann.headers)
    assert renamed.json()["name"] == "New"
    described = await client.patch(f"{W}/{ws}", json={"description": "About"}, headers=ann.headers)
    assert described.json()["description"] == "About"
    cleared = await client.patch(f"{W}/{ws}", json={"description": ""}, headers=ann.headers)
    assert cleared.json()["description"] is None
    by_member = await client.patch(f"{W}/{ws}", json={"name": "X"}, headers=bob.headers)
    assert by_member.status_code == 403


async def test_add_members(client: httpx.AsyncClient, make_user) -> None:
    ann, bob, cat = await make_user("ann"), await make_user("bob"), await make_user("cat")
    ws = await create(client, ann)

    by_name = await add(client, ws, ann, "bob")
    assert by_name.status_code == 201
    assert by_name.json()["roles"] == ["member"]
    assert (await add(client, ws, ann, "CAT@example.com")).status_code == 201  # by email

    assert code(await add(client, ws, ann, "bob")) == "already_member"
    assert code(await add(client, ws, ann, "ann")) == "already_owner"
    assert code(await add(client, ws, ann, "nobody")) == "user_not_found"
    # Only the owner adds people.
    await make_user("dan")
    assert (await add(client, ws, bob, "dan")).status_code == 403

    members = await client.get(f"{W}/{ws}/members", headers=cat.headers)
    assert [m["username"] for m in members.json()] == ["bob", "cat"]

    mine = await client.get(W, headers=bob.headers)
    assert [(w["id"], w["my_roles"]) for w in mine.json()] == [(ws, ["member"])]


async def test_roles(client: httpx.AsyncClient, make_user) -> None:
    ann, bob, cat = await make_user("ann"), await make_user("bob"), await make_user("cat")
    dan = await make_user("dan")
    ws = await create(client, ann)
    for name in ("bob", "cat"):
        await add(client, ws, ann, name)

    # Owner grants editor; an editor grants reviewer.
    assert (await grant(client, ws, ann, bob, "editor")).json()["roles"] == ["editor", "member"]
    assert (await grant(client, ws, bob, cat, "reviewer")).json()["roles"] == [
        "member",
        "reviewer",
    ]

    # An editor cannot grant editor; a plain member cannot grant anything.
    assert (await grant(client, ws, bob, cat, "editor")).status_code == 403
    assert (await grant(client, ws, cat, bob, "reviewer")).status_code == 403
    # Roles only on top of 'member'; 'member' itself goes through /members.
    assert code(await grant(client, ws, ann, dan, "reviewer")) == "member_not_found"
    assert code(await grant(client, ws, ann, cat, "member")) == "role_not_grantable"
    assert code(await grant(client, ws, ann, cat, "reviewer")) == "role_already_granted"

    revoked = await client.delete(f"{W}/{ws}/members/{cat.id}/roles/reviewer", headers=bob.headers)
    assert revoked.json()["roles"] == ["member"]

    # Removing a person removes all their roles.
    removed = await client.delete(f"{W}/{ws}/members/{bob.id}", headers=ann.headers)
    assert removed.status_code == 204
    assert (await client.get(f"{W}/{ws}", headers=bob.headers)).status_code == 404


async def test_activity_log(client: httpx.AsyncClient, make_user) -> None:
    ann, bob, cat = await make_user("ann"), await make_user("bob"), await make_user("cat")
    ws = await create(client, ann)
    await add(client, ws, ann, "bob")
    await add(client, ws, ann, "cat")
    await grant(client, ws, ann, bob, "editor")

    log = await client.get(f"{W}/{ws}/activity", headers=ann.headers)
    assert [(e["action"], e["target_label"]) for e in log.json()] == [
        ("role_added", "bob"),
        ("member_added", "cat"),
        ("member_added", "bob"),
    ]
    assert log.json()[0]["actor_name"] == "ann"
    assert log.json()[0]["details"] == {"role": "editor"}

    assert (await client.get(f"{W}/{ws}/activity", headers=bob.headers)).status_code == 200
    assert (await client.get(f"{W}/{ws}/activity", headers=cat.headers)).status_code == 403


async def test_archive_private(client: httpx.AsyncClient, make_user) -> None:
    ann, bob = await make_user("ann"), await make_user("bob")
    ws = await create(client, ann)
    await add(client, ws, ann, "bob")

    archived = await client.post(f"{W}/{ws}/archive", headers=ann.headers)
    assert archived.json()["archived_at"] is not None
    assert archived.json()["owner_id"] == ann.id  # private: owner stays

    # Memberships are gone and the workspace is read-only.
    assert (await client.get(f"{W}/{ws}", headers=bob.headers)).status_code == 404
    assert code(await add(client, ws, ann, "bob")) == "workspace_archived"

    unarchived = await client.post(f"{W}/{ws}/unarchive", headers=ann.headers)
    assert unarchived.json()["archived_at"] is None


async def test_archive_public_and_take(client: httpx.AsyncClient, make_user) -> None:
    ann, bob, cat = await make_user("ann"), await make_user("bob"), await make_user("cat")
    ws = await create(client, ann)
    await client.post(f"{W}/{ws}/make-public", headers=ann.headers)

    archived = await client.post(f"{W}/{ws}/archive", headers=ann.headers)
    assert archived.json()["owner_id"] is None  # public: free for anyone
    assert [w["id"] for w in (await client.get(W, params={"scope": "free"})).json()] == [ws]

    taken = await client.post(f"{W}/{ws}/take", headers=bob.headers)
    assert taken.json()["owner_id"] == bob.id
    assert taken.json()["archived_at"] is None
    assert code(await client.post(f"{W}/{ws}/take", headers=cat.headers)) == "workspace_not_free"


async def test_delete_only_empty(client: httpx.AsyncClient, make_user, db: AsyncSession) -> None:
    ann = await make_user("ann")
    empty, used = await create(client, ann, "Empty"), await create(client, ann, "Used")

    # A task in "Used" (built directly: the tasks API comes in a later step).
    pipeline_id = await db.scalar(select(Pipeline.id).where(Pipeline.name == "research"))
    version = PipelineVersion(
        pipeline_id=pipeline_id, version_name="1.0.0", version_code=1, file_path="p", file_hash="h"
    )
    model = Model(provider_id=1, name="test-model", context_length=4096)
    db.add_all([version, model])
    await db.flush()
    db.add(
        Task(
            workspace_id=used,
            pipeline_version_id=version.id,
            model_id=model.id,
            title="T",
            input="q",
        )
    )
    await db.commit()

    assert (await client.delete(f"{W}/{empty}", headers=ann.headers)).status_code == 204
    assert (await client.get(f"{W}/{empty}", headers=ann.headers)).status_code == 404
    assert code(await client.delete(f"{W}/{used}", headers=ann.headers)) == "workspace_not_empty"


async def test_admin_sees_private_by_link_only(
    client: httpx.AsyncClient, make_user, db: AsyncSession
) -> None:
    ann, root = await make_user("ann"), await make_user("root")
    await grant_admin(db, root.id, granted_by="test")
    ws = await create(client, ann)

    assert (await client.get(f"{W}/{ws}", headers=root.headers)).status_code == 200
    assert (await client.get(f"{W}/{ws}/members", headers=root.headers)).status_code == 200
    # Not in lists, and read-only.
    assert (await client.get(W, params={"scope": "public"}, headers=root.headers)).json() == []
    assert (await add(client, ws, root, "ann")).status_code == 403


async def test_member_leaves(client: httpx.AsyncClient, make_user) -> None:
    ann, bob = await make_user("ann"), await make_user("bob")
    ws = await create(client, ann)
    await add(client, ws, ann, "bob")
    await grant(client, ws, ann, bob, "editor")

    assert (await client.post(f"{W}/{ws}/leave", headers=bob.headers)).status_code == 204
    assert (await client.get(f"{W}/{ws}", headers=bob.headers)).status_code == 404
    log = await client.get(f"{W}/{ws}/activity", headers=ann.headers)
    assert log.json()[0]["action"] == "member_removed"
    assert log.json()[0]["details"] == {"left": True}

    # The owner cannot leave (not a member); they archive or delete instead.
    assert code(await client.post(f"{W}/{ws}/leave", headers=ann.headers)) == "member_not_found"
