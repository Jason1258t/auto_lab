"""Tasks API: who can do what, and which status changes are allowed."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Pipeline, PipelineVersion, Publication, Publisher, Work
from tests.conftest import ApiUser, Catalog

API = "/api/v1"


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


async def workspace(client: httpx.AsyncClient, owner: ApiUser) -> int:
    return (
        await client.post(f"{API}/workspaces", json={"name": "Lab"}, headers=owner.headers)
    ).json()["id"]


async def add_member(client, ws: int, owner: ApiUser, user: ApiUser, *roles: str) -> None:
    await client.post(
        f"{API}/workspaces/{ws}/members",
        json={"username_or_email": user.username},
        headers=owner.headers,
    )
    for role in roles:
        await client.put(
            f"{API}/workspaces/{ws}/members/{user.id}/roles/{role}", headers=owner.headers
        )


async def new_task(
    client: httpx.AsyncClient, ws: int, by: ApiUser, catalog: Catalog, **extra
) -> httpx.Response:
    body = {
        "title": "Why is the sky blue?",
        "input": "Explain Rayleigh scattering with sources.",
        "pipeline_id": catalog.pipeline_id,
        "model_id": catalog.model_id,
        **extra,
    }
    return await client.post(f"{API}/workspaces/{ws}/tasks", json=body, headers=by.headers)


async def test_create_and_read(client: httpx.AsyncClient, make_user, catalog: Catalog) -> None:
    ann, bob = await make_user("ann"), await make_user("bob")
    ws = await workspace(client, ann)
    await add_member(client, ws, ann, bob)

    created = await new_task(client, ws, ann, catalog)
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "draft"
    assert task["pipeline_name"] == "research"
    assert task["pipeline_version"] == "1.0.0"
    assert task["reviewer_id"] == ann.id  # the creator by default

    # Members read tasks; the list is newest first.
    second = (await new_task(client, ws, ann, catalog, title="Second")).json()
    listed = await client.get(f"{API}/workspaces/{ws}/tasks", headers=bob.headers)
    assert [t["id"] for t in listed.json()] == [second["id"], task["id"]]
    detail = await client.get(f"{API}/tasks/{task['id']}", headers=bob.headers)
    assert detail.json()["steps"] == []


async def test_who_can_create(client: httpx.AsyncClient, make_user, catalog: Catalog) -> None:
    ann, ed, mem = await make_user("ann"), await make_user("eddy"), await make_user("mem")
    out = await make_user("out")
    ws = await workspace(client, ann)
    await add_member(client, ws, ann, ed, "editor")
    await add_member(client, ws, ann, mem, "reviewer")

    assert (await new_task(client, ws, ed, catalog)).status_code == 201
    assert (await new_task(client, ws, mem, catalog)).status_code == 403
    assert (await new_task(client, ws, out, catalog)).status_code == 404


async def test_tasks_hidden_in_public_workspace(
    client: httpx.AsyncClient, make_user, catalog: Catalog
) -> None:
    ann, out = await make_user("ann"), await make_user("out")
    ws = await workspace(client, ann)
    task_id = (await new_task(client, ws, ann, catalog)).json()["id"]
    await client.post(f"{API}/workspaces/{ws}/make-public", headers=ann.headers)

    # Only works are public, not tasks.
    assert (await client.get(f"{API}/tasks/{task_id}", headers=out.headers)).status_code == 404
    listed = await client.get(f"{API}/workspaces/{ws}/tasks", headers=out.headers)
    assert listed.status_code == 403


async def test_create_checks(
    client: httpx.AsyncClient, make_user, catalog: Catalog, db: AsyncSession
) -> None:
    ann, out = await make_user("ann"), await make_user("out")
    ws = await workspace(client, ann)

    assert code(await new_task(client, ws, ann, catalog, model_id=999_999)) == "model_not_found"
    assert code(await new_task(client, ws, ann, catalog, reviewer_id=out.id)) == (
        "reviewer_not_member"
    )
    no_reviewer = await new_task(client, ws, ann, catalog, reviewer_id=None)
    assert no_reviewer.json()["reviewer_id"] is None

    empty = Pipeline(name="empty_pipeline")
    db.add(empty)
    await db.commit()
    assert code(await new_task(client, ws, ann, catalog, pipeline_id=empty.id)) == (
        "pipeline_has_no_versions"
    )


async def test_newest_pipeline_version(
    client: httpx.AsyncClient, make_user, catalog: Catalog, db: AsyncSession
) -> None:
    ann = await make_user("ann")
    ws = await workspace(client, ann)
    db.add(
        PipelineVersion(
            pipeline_id=catalog.pipeline_id,
            version_name="1.1.0",
            version_code=2,
            file_path="pipelines/research/1.1.0.yaml",
            file_hash="test2",
        )
    )
    await db.commit()
    assert (await new_task(client, ws, ann, catalog)).json()["pipeline_version"] == "1.1.0"


async def test_edit_only_draft(client: httpx.AsyncClient, make_user, catalog: Catalog) -> None:
    ann, bob = await make_user("ann"), await make_user("bob")
    ws = await workspace(client, ann)
    await add_member(client, ws, ann, bob, "reviewer")
    task_id = (await new_task(client, ws, ann, catalog)).json()["id"]

    edited = await client.patch(
        f"{API}/tasks/{task_id}", json={"title": "Better title"}, headers=ann.headers
    )
    assert edited.json()["title"] == "Better title"

    await client.post(f"{API}/tasks/{task_id}/queue", headers=ann.headers)
    late = await client.patch(f"{API}/tasks/{task_id}", json={"title": "X"}, headers=ann.headers)
    assert code(late) == "task_not_draft"
    # The reviewer can still change.
    reviewer = await client.patch(
        f"{API}/tasks/{task_id}", json={"reviewer_id": bob.id}, headers=ann.headers
    )
    assert reviewer.json()["reviewer_id"] == bob.id


async def test_queue_and_cancel(client: httpx.AsyncClient, make_user, catalog: Catalog) -> None:
    ann = await make_user("ann")
    ws = await workspace(client, ann)
    task_id = (await new_task(client, ws, ann, catalog)).json()["id"]

    assert code(await client.post(f"{API}/tasks/{task_id}/cancel", headers=ann.headers)) == (
        "task_not_cancellable"
    )
    queued = await client.post(f"{API}/tasks/{task_id}/queue", headers=ann.headers)
    assert queued.json()["status"] == "queued"
    assert code(await client.post(f"{API}/tasks/{task_id}/queue", headers=ann.headers)) == (
        "task_not_draft"
    )
    cancelled = await client.post(f"{API}/tasks/{task_id}/cancel", headers=ann.headers)
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None


async def test_delete(
    client: httpx.AsyncClient, make_user, catalog: Catalog, db: AsyncSession
) -> None:
    ann = await make_user("ann")
    ws = await workspace(client, ann)
    task = (await new_task(client, ws, ann, catalog)).json()

    assert (
        await client.delete(f"{API}/tasks/{task['id']}", headers=ann.headers)
    ).status_code == 204
    assert (await client.get(f"{API}/tasks/{task['id']}", headers=ann.headers)).status_code == 404
    log = await client.get(f"{API}/workspaces/{ws}/activity", headers=ann.headers)
    assert (log.json()[0]["action"], log.json()[0]["target_label"]) == (
        "task_deleted",
        task["title"],
    )

    # A published work protects its task.
    published = (await new_task(client, ws, ann, catalog)).json()["id"]
    publisher = Publisher(name="Ann Lab", owner_id=ann.id)
    db.add_all([Work(task_id=published, file_path="w.md"), publisher])
    await db.flush()
    db.add(Publication(work_id=published, publisher_id=publisher.id, title="Public"))
    await db.commit()
    blocked = await client.delete(f"{API}/tasks/{published}", headers=ann.headers)
    assert code(blocked) == "task_published"
