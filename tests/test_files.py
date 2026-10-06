"""Workspace files: upload, list, download, remove, and who can do it."""

import hashlib
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import WorkspaceFile
from autolab.services.files import safe_name, store_file
from tests.conftest import ApiUser

API = "/api/v1"
CONTENT = b"# Week 1\nRayleigh scattering makes the sky blue.\n"


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


async def setup(client: httpx.AsyncClient, make_user) -> tuple[int, ApiUser, ApiUser, ApiUser]:
    """A workspace of ann, with bob as editor and cat as plain member."""
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
    await client.put(f"{API}/workspaces/{ws}/members/{bob.id}/roles/editor", headers=ann.headers)
    return ws, ann, bob, cat


async def upload(
    client: httpx.AsyncClient, ws: int, user: ApiUser, name: str = "Week 1 notes.md", **form
) -> httpx.Response:
    return await client.post(
        f"{API}/workspaces/{ws}/files",
        files={"file": (name, CONTENT, "text/markdown")},
        data=form,
        headers=user.headers,
    )


def test_safe_name() -> None:
    assert safe_name("Week 1 notes.md") == "Week_1_notes.md"
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("C:\\Users\\ann\\essay (final).docx") == "essay_final_.docx"
    assert safe_name("...") == "file"


async def test_upload_and_download(
    client: httpx.AsyncClient, make_user, settings: Settings
) -> None:
    ws, _, bob, cat = await setup(client, make_user)

    response = await upload(client, ws, bob, original_path="course/week 1/Week 1 notes.md")
    assert response.status_code == 201
    file = response.json()
    assert file["original_name"] == "Week 1 notes.md"
    assert file["original_path"] == "course/week 1/Week 1 notes.md"
    assert file["file_name"] == f"{file['id']}_Week_1_notes.md"
    assert file["size_bytes"] == len(CONTENT)
    assert file["sha256"] == hashlib.sha256(CONTENT).hexdigest()

    on_disk = Path(settings.data_dir) / "workspaces" / str(ws) / "files" / file["file_name"]
    assert on_disk.read_bytes() == CONTENT

    # Any member can list and download; the download keeps the original name.
    listed = await client.get(f"{API}/workspaces/{ws}/files", headers=cat.headers)
    assert [f["id"] for f in listed.json()] == [file["id"]]
    download = await client.get(
        f"{API}/workspaces/{ws}/files/{file['id']}/download", headers=cat.headers
    )
    assert download.content == CONTENT
    assert "Week%201%20notes.md" in download.headers["content-disposition"]


async def test_who_can_change_files(client: httpx.AsyncClient, make_user) -> None:
    ws, ann, bob, cat = await setup(client, make_user)
    out = await make_user("out")

    assert (await upload(client, ws, ann)).status_code == 201
    assert (await upload(client, ws, cat)).status_code == 403  # plain member
    assert (await upload(client, ws, out)).status_code == 404  # outsider
    file_id = (await upload(client, ws, bob)).json()["id"]

    assert (
        await client.delete(f"{API}/workspaces/{ws}/files/{file_id}", headers=cat.headers)
    ).status_code == 403
    assert (
        await client.get(f"{API}/workspaces/{ws}/files", headers=out.headers)
    ).status_code == 404


async def test_remove_file(client: httpx.AsyncClient, make_user, settings: Settings) -> None:
    ws, ann, _, _ = await setup(client, make_user)
    file = (await upload(client, ws, ann)).json()
    on_disk = Path(settings.data_dir) / "workspaces" / str(ws) / "files" / file["file_name"]

    removed = await client.delete(f"{API}/workspaces/{ws}/files/{file['id']}", headers=ann.headers)
    assert removed.status_code == 204
    assert not on_disk.exists()

    log = await client.get(f"{API}/workspaces/{ws}/activity", headers=ann.headers)
    assert [(e["action"], e["target_label"]) for e in log.json()[:2]] == [
        ("file_removed", "Week 1 notes.md"),
        ("file_added", "Week 1 notes.md"),
    ]


async def test_too_large(
    client: httpx.AsyncClient, make_user, settings: Settings, db: AsyncSession
) -> None:
    ws, ann, _, _ = await setup(client, make_user)
    settings.max_upload_bytes = 10

    response = await upload(client, ws, ann)
    assert code(response) == "file_too_large"
    assert await db.scalar(select(WorkspaceFile)) is None
    # No temp file is left behind.
    folder = Path(settings.data_dir) / "workspaces" / str(ws) / "files"
    assert list(folder.iterdir()) == []


async def test_archived_is_read_only(client: httpx.AsyncClient, make_user) -> None:
    ws, ann, _, _ = await setup(client, make_user)
    file_id = (await upload(client, ws, ann)).json()["id"]
    await client.post(f"{API}/workspaces/{ws}/archive", headers=ann.headers)

    assert code(await upload(client, ws, ann)) == "workspace_archived"
    # Still readable by the owner.
    assert (
        await client.get(f"{API}/workspaces/{ws}/files/{file_id}/download", headers=ann.headers)
    ).status_code == 200


async def test_delete_workspace_removes_folder(
    client: httpx.AsyncClient, make_user, settings: Settings
) -> None:
    ws, ann, _, _ = await setup(client, make_user)
    await upload(client, ws, ann)
    folder = Path(settings.data_dir) / "workspaces" / str(ws)
    assert folder.exists()

    assert (await client.delete(f"{API}/workspaces/{ws}", headers=ann.headers)).status_code == 204
    assert not folder.exists()


async def test_store_from_server_disk(
    client: httpx.AsyncClient, make_user, settings: Settings, db: AsyncSession, tmp_path: Path
) -> None:
    """What `autolab add-file` does: copy a file from the server's disk."""
    ws, _, _, _ = await setup(client, make_user)
    source = tmp_path / "Lecture 3.txt"
    source.write_bytes(CONTENT)

    async def chunks():
        yield source.read_bytes()

    stored = await store_file(
        db,
        settings,
        workspace_id=ws,
        chunks=chunks(),
        original_name=source.name,
        original_path=str(source),
        content_type="text/plain",
        actor=None,
    )
    assert stored.original_path == str(source)
    assert stored.uploaded_by is None
    assert (Path(settings.data_dir) / "workspaces" / str(ws) / "files" / stored.file_name).exists()
