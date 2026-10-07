"""The review cycle through the API, with the worker and a fake model:
run -> reject with a comment -> revise -> accept. Also works and calls."""

import shutil
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Model, Pipeline, TaskStep
from autolab.logstore import FileLogStore
from autolab.worker.main import Worker
from autolab.worker.runner import task_dir
from tests.conftest import ApiUser
from tests.fakes import FakeAdapter
from tests.test_research import fake_model, fake_resolver, fake_web

API = "/api/v1"


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
async def lab(
    client: httpx.AsyncClient,
    make_user,
    session_factory,
    settings: Settings,
    tmp_path: Path,
    db: AsyncSession,
):
    """A workspace of ann (bob: reviewer role, cat: plain member), a
    research task that the worker has run, and the worker."""
    folder = tmp_path / "pipelines" / "research"
    folder.mkdir(parents=True)
    shutil.copy("pipelines/research/1.0.0.yaml", folder)
    settings.pipelines_dir = str(folder.parent)
    settings.searxng_url = "http://searx.test"

    adapter = FakeAdapter(fake_model)
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_web))
    log_store = FileLogStore(Path(settings.data_dir) / "logs")
    client._transport.app.state.log_store = log_store  # the API reads the same logs
    worker = Worker(
        session_factory, settings, log_store, {"ollama": adapter}, http=http, resolver=fake_resolver
    )
    await worker.start()

    model = Model(provider_id=1, name="fake-model", context_length=4096)
    db.add(model)
    await db.commit()
    pipeline_id = await db.scalar(select(Pipeline.id).where(Pipeline.name == "research"))

    ann, bob, cat = await make_user("ann"), await make_user("bob"), await make_user("cat")
    ws = (await client.post(f"{API}/workspaces", json={"name": "Lab"}, headers=ann.headers)).json()[
        "id"
    ]
    for user in (bob, cat):
        await client.post(
            f"{API}/workspaces/{ws}/members",
            json={"username_or_email": user.username},
            headers=ann.headers,
        )
    await client.put(f"{API}/workspaces/{ws}/members/{bob.id}/roles/reviewer", headers=ann.headers)
    task = await client.post(
        f"{API}/workspaces/{ws}/tasks",
        json={
            "title": "Sky",
            "input": "Why is the sky blue?",
            "pipeline_id": pipeline_id,
            "model_id": model.id,
        },
        headers=ann.headers,
    )
    task_id = task.json()["id"]
    await client.post(f"{API}/tasks/{task_id}/queue", headers=ann.headers)
    assert await worker.run_once()
    yield {
        "ws": ws,
        "task": task_id,
        "ann": ann,
        "bob": bob,
        "cat": cat,
        "worker": worker,
        "adapter": adapter,
    }
    await http.aclose()


async def review(client: httpx.AsyncClient, task_id: int, user: ApiUser, **body) -> httpx.Response:
    return await client.post(f"{API}/tasks/{task_id}/reviews", json=body, headers=user.headers)


async def status(client: httpx.AsyncClient, task_id: int, user: ApiUser) -> str:
    return (await client.get(f"{API}/tasks/{task_id}", headers=user.headers)).json()["status"]


async def test_reject_revise_accept(
    client: httpx.AsyncClient, lab, db: AsyncSession, settings: Settings
) -> None:
    task_id, ann, bob, cat = lab["task"], lab["ann"], lab["bob"], lab["cat"]
    adapter = lab["adapter"]
    assert await status(client, task_id, ann) == "in_review"

    # Who may review: not a plain member; a rejection needs a comment.
    assert (await review(client, task_id, cat, result="accepted")).status_code == 403
    assert code(await review(client, task_id, bob, result="rejected")) == "comment_required"

    rejected = await review(
        client, task_id, bob, result="rejected", comment="Add the sunset colors."
    )
    assert rejected.status_code == 201
    assert await status(client, task_id, ann) == "queued"

    calls_before = len(adapter.requests)
    assert await lab["worker"].run_once()
    assert await status(client, task_id, ann) == "in_review"

    # Only synthesize and write ran again (revise.rerun_from = synthesize),
    # each with the reviewer's comment in the prompt.
    revise_requests = adapter.requests[calls_before:]
    systems = [r.messages[0].content.split(".")[0] for r in revise_requests]
    assert systems == [
        "You plan the structure of a short report",
        "You write one clear paragraph of a report",
    ]
    assert all("Add the sunset colors." in r.messages[-1].content for r in revise_requests)
    rows = (
        await db.scalars(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.step_index)
        )
    ).all()
    review_id = rejected.json()["id"]
    assert [(r.step_index, r.review_id) for r in rows[7:]] == [(7, review_id), (8, review_id)]

    accepted = await review(client, task_id, bob, result="accepted")
    assert accepted.status_code == 201
    assert await status(client, task_id, ann) == "done"
    assert not task_dir(settings, task_id).exists()  # step files are not kept
    assert code(await review(client, task_id, bob, result="accepted")) == "task_not_in_review"

    history = await client.get(f"{API}/tasks/{task_id}/reviews", headers=cat.headers)
    assert [r["result"] for r in history.json()] == ["rejected", "accepted"]


async def test_work_visibility(client: httpx.AsyncClient, lab, make_user) -> None:
    task_id, ws, ann, bob = lab["task"], lab["ws"], lab["ann"], lab["bob"]
    out = await make_user("out")

    work = await client.get(f"{API}/tasks/{task_id}/work", headers=ann.headers)
    assert work.status_code == 200
    assert work.json()["text"].startswith("# Sky")
    assert work.json()["workspace_id"] == ws
    [source] = work.json()["sources"]
    assert source["location"] == "http://site-a.test/sky"
    assert source["quotes"][0]["quote"] == "The sky looks blue because of Rayleigh scattering."

    # Private: hidden from outsiders. Public: only accepted works.
    assert (await client.get(f"{API}/tasks/{task_id}/work", headers=out.headers)).status_code == 404
    await client.post(f"{API}/workspaces/{ws}/make-public", headers=ann.headers)
    assert (await client.get(f"{API}/tasks/{task_id}/work")).status_code == 404
    assert (await client.get(f"{API}/workspaces/{ws}/works")).json() == []

    await review(client, task_id, bob, result="accepted")
    assert (await client.get(f"{API}/tasks/{task_id}/work")).status_code == 200
    assert [w["task_id"] for w in (await client.get(f"{API}/workspaces/{ws}/works")).json()] == [
        task_id
    ]


async def test_calls_and_logs(client: httpx.AsyncClient, lab, make_user) -> None:
    task_id, ann = lab["task"], lab["ann"]
    out = await make_user("out")

    calls = (await client.get(f"{API}/tasks/{task_id}/calls", headers=ann.headers)).json()
    # plan, summarize, verify (one fact left after the quote check), synthesize, write
    assert len(calls) == 5
    assert all(c["status"] == "done" and c["valid_json"] for c in calls)

    log = await client.get(f"{API}/calls/{calls[0]['id']}/log", headers=ann.headers)
    body = log.json()
    assert "Why is the sky blue?" in body["request"]["messages"][-1]["content"]
    assert body["request"]["schema"]["required"] == ["queries"]  # the alias, not schema_
    assert body["response"]["text"]
    assert (
        await client.get(f"{API}/calls/{calls[0]['id']}/log", headers=out.headers)
    ).status_code == 404
