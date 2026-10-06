"""Publishers and publications: who may publish what, and the public feed."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.services.admins import grant_admin
from tests.test_reviews import lab  # noqa: F401  (the fixture)

API = "/api/v1"


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


async def publisher(client: httpx.AsyncClient, user, name: str = "Ann Lab") -> int:
    response = await client.post(f"{API}/publishers", json={"name": name}, headers=user.headers)
    return response.json()["id"]


async def publish(client, user, task_id: int, publisher_id: int) -> httpx.Response:
    body = {"task_id": task_id, "publisher_id": publisher_id, "title": "Why the sky is blue"}
    return await client.post(f"{API}/publications", json=body, headers=user.headers)


async def test_publish_rules(client: httpx.AsyncClient, lab) -> None:  # noqa: F811
    task_id, ann, bob = lab["task"], lab["ann"], lab["bob"]
    mine = await publisher(client, ann)
    bobs = await publisher(client, bob, "Bob Press")
    taken = await client.post(f"{API}/publishers", json={"name": "Ann Lab"}, headers=bob.headers)
    assert code(taken) == "publisher_exists"

    # Not accepted yet.
    assert code(await publish(client, ann, task_id, mine)) == "task_not_accepted"
    await client.post(
        f"{API}/tasks/{task_id}/reviews", json={"result": "accepted"}, headers=bob.headers
    )

    # Only the workspace owner, only under their own publisher.
    assert (await publish(client, bob, task_id, bobs)).status_code == 403
    assert (await publish(client, ann, task_id, bobs)).status_code == 403
    published = await publish(client, ann, task_id, mine)
    assert published.status_code == 201
    assert published.json()["publisher"]["name"] == "Ann Lab"
    assert code(await publish(client, ann, task_id, mine)) == "already_published"

    log = await client.get(f"{API}/workspaces/{lab['ws']}/activity", headers=ann.headers)
    assert log.json()[0]["action"] == "work_published"


async def test_public_feed(client: httpx.AsyncClient, lab, db: AsyncSession) -> None:  # noqa: F811
    task_id, ann, bob = lab["task"], lab["ann"], lab["bob"]
    await client.post(
        f"{API}/tasks/{task_id}/reviews", json={"result": "accepted"}, headers=bob.headers
    )
    publication_id = (await publish(client, ann, task_id, await publisher(client, ann))).json()[
        "id"
    ]

    # The workspace is private, but the publication is public, without login.
    feed = await client.get(f"{API}/publications")
    assert [p["id"] for p in feed.json()] == [publication_id]
    detail = await client.get(f"{API}/publications/{publication_id}")
    assert detail.json()["text"].startswith("# Sky")
    assert detail.json()["sources"][0]["quotes"][0]["quote"].startswith("The sky looks blue")
    assert "workspace" not in detail.text

    # A published work protects its task, until an admin removes the publication.
    assert code(await client.delete(f"{API}/tasks/{task_id}", headers=ann.headers)) == (
        "task_published"
    )
    await grant_admin(db, ann.id, granted_by="test")
    removed = await client.delete(f"{API}/admin/publications/{publication_id}", headers=ann.headers)
    assert removed.status_code == 204
    assert (await client.delete(f"{API}/tasks/{task_id}", headers=ann.headers)).status_code == 204
