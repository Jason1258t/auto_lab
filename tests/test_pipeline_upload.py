"""Uploading pipelines in the admin page."""

from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import ActivityEvent, PipelineVersion
from autolab.services.admins import grant_admin
from autolab_engine.pipelines import file_hash, load_pipeline

API = "/api/v1"
CODE_FILE = Path("pipelines/code/1.0.0.yaml").read_bytes()


async def upload(client, user, name: str, version: str, content: bytes = CODE_FILE, dry_run=False):
    return await client.post(
        f"{API}/admin/pipelines/upload",
        data={"name": name, "version": version, "dry_run": str(dry_run).lower()},
        files={"file": ("p.yaml", content, "application/x-yaml")},
        headers=user.headers,
    )


async def admin(make_user, db: AsyncSession, name: str = "root"):
    user = await make_user(name)
    await grant_admin(db, user.id, granted_by="test")
    return user


async def test_upload_a_new_pipeline(
    client: httpx.AsyncClient, make_user, db: AsyncSession, settings: Settings
) -> None:
    root = await admin(make_user, db)
    # Only admins.
    ann = await make_user("ann")
    assert (await upload(client, ann, "my_code", "1.0.0")).status_code == 403

    # A check first: nothing is saved.
    checked = await upload(client, root, "my_code", "1.0.0", dry_run=True)
    assert checked.status_code == 201, checked.text
    assert checked.json()["saved"] is False
    assert not (Path(settings.uploaded_pipelines_dir) / "my_code").exists()

    created = await upload(client, root, "my_code", "1.0.0")
    body = created.json()
    assert body["saved"] is True and body["created_pipeline"] is True
    # The fields win over the file's own lines (it says "code").
    assert "'pipeline' in the file was code; set to my_code" in body["notes"]

    path = Path(settings.uploaded_pipelines_dir) / "my_code" / "1.0.0.yaml"
    loaded = load_pipeline(path)  # valid, and matches its folder and file name
    assert (loaded.pipeline, loaded.version) == ("my_code", "1.0.0")
    version = await db.get(PipelineVersion, body["version_id"])
    assert version.file_hash == file_hash(path)  # the worker's check will pass

    # New tasks can use it at once: the public catalog lists it.
    catalog = (await client.get(f"{API}/pipelines")).json()
    assert {"name": "my_code", "version_name": "1.0.0"}.items() <= next(
        p for p in catalog if p["name"] == "my_code"
    ).items()

    # The admin list shows it as uploaded, with its YAML.
    listed = (await client.get(f"{API}/admin/pipelines", headers=root.headers)).json()
    mine = next(p for p in listed if p["name"] == "my_code")
    assert [(v["version_name"], v["uploaded"]) for v in mine["versions"]] == [("1.0.0", True)]
    text = await client.get(
        f"{API}/admin/pipeline-versions/{body['version_id']}/file", headers=root.headers
    )
    assert text.text.startswith("# Pipeline") and "pipeline: my_code" in text.text

    event = await db.scalar(
        select(ActivityEvent).where(ActivityEvent.action == "pipeline_uploaded")
    )
    assert event.target_label == "my_code 1.0.0"


async def test_new_version_must_be_newer(client: httpx.AsyncClient, make_user, db) -> None:
    root = await admin(make_user, db)
    assert (await upload(client, root, "my_code", "1.1.0")).status_code == 201
    older = await upload(client, root, "my_code", "1.0.5")
    assert older.status_code == 409
    assert older.json()["error"]["code"] == "pipeline_version_not_newer"
    assert (await upload(client, root, "my_code", "1.2.0")).status_code == 201


async def test_invalid_files_are_explained(client: httpx.AsyncClient, make_user, db) -> None:
    root = await admin(make_user, db)
    broken = CODE_FILE.replace(b"kind: code_check", b"kind: run_shell")
    answer = await upload(client, root, "my_code", "1.0.0", broken)
    assert answer.status_code == 422
    assert "unknown kind 'run_shell'" in answer.json()["error"]["message"]

    not_yaml = await upload(client, root, "my_code", "1.0.0", b"steps: [unclosed")
    assert not_yaml.json()["error"]["code"] == "invalid_pipeline"

    bad_name = await upload(client, root, "My Code!", "1.0.0")
    assert bad_name.json()["error"]["code"] == "invalid_pipeline_name"
    bad_version = await upload(client, root, "my_code", "v1")
    assert bad_version.json()["error"]["code"] == "invalid_pipeline_version"
