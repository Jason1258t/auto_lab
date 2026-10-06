"""User files of a workspace.

A file is copied into data/workspaces/<workspace_id>/files/ under a new,
safe name "<id>_<cleaned original name>". The row keeps the original name
and path (for people) and the current name on disk.
"""

import asyncio
import hashlib
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import User, WorkspaceFile
from autolab.errors import AppError
from autolab.services import activity
from autolab.services.permissions import (
    WorkspaceAccess,
    forbidden,
    require_inside,
    require_not_archived,
)

CHUNK_SIZE = 1024 * 1024
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def workspace_dir(settings: Settings, workspace_id: int) -> Path:
    return Path(settings.data_dir) / "workspaces" / str(workspace_id) / "files"


def file_path(settings: Settings, file: WorkspaceFile) -> Path:
    return workspace_dir(settings, file.workspace_id) / file.file_name


def safe_name(original_name: str) -> str:
    """Only letters, digits, '.', '_' and '-'; no folders. "../a b.pdf"
    becomes "a_b.pdf"."""
    name = _UNSAFE.sub("_", Path(original_name.replace("\\", "/")).name).strip("._")
    return name[:100] or "file"


def file_not_found(file_id: int) -> AppError:
    return AppError(404, "file_not_found", f"File {file_id} not found")


async def _write_temp(
    folder: Path, chunks: AsyncIterator[bytes], max_bytes: int
) -> tuple[Path, int, str]:
    """Write the chunks to a temp file. Returns (path, size, sha256)."""
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    temp = folder / f".upload-{uuid.uuid4().hex}"
    digest = hashlib.sha256()
    size = 0
    try:
        with temp.open("wb") as out:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(
                        413, "file_too_large", f"The file is larger than {max_bytes} bytes"
                    )
                digest.update(chunk)
                await asyncio.to_thread(out.write, chunk)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return temp, size, digest.hexdigest()


async def store_file(
    db: AsyncSession,
    settings: Settings,
    *,
    workspace_id: int,
    chunks: AsyncIterator[bytes],
    original_name: str,
    original_path: str | None,
    content_type: str | None,
    actor: User | None,
) -> WorkspaceFile:
    """Copy a file into the workspace folder and add its row. No access
    check here: the API checks before (add_file), the CLI is for admins."""
    folder = workspace_dir(settings, workspace_id)
    temp, size, sha256 = await _write_temp(folder, chunks, settings.max_upload_bytes)
    final: Path | None = None
    try:
        # The final name needs the row id, so insert first with the temp name.
        file = WorkspaceFile(
            workspace_id=workspace_id,
            original_name=original_name,
            original_path=original_path,
            file_name=temp.name,
            size_bytes=size,
            sha256=sha256,
            content_type=content_type,
            uploaded_by=actor.id if actor else None,
        )
        db.add(file)
        await db.flush()
        file.file_name = f"{file.id}_{safe_name(original_name)}"
        final = folder / file.file_name
        temp.rename(final)
        activity.record(
            db,
            "file_added",
            actor=actor,
            workspace_id=workspace_id,
            target_type="file",
            target_id=file.id,
            target_label=original_name,
        )
        await db.commit()
        return file
    except BaseException:
        temp.unlink(missing_ok=True)
        if final is not None:
            final.unlink(missing_ok=True)
        raise


async def add_file(
    db: AsyncSession,
    settings: Settings,
    access: WorkspaceAccess,
    *,
    chunks: AsyncIterator[bytes],
    original_name: str,
    original_path: str | None,
    content_type: str | None,
) -> WorkspaceFile:
    if not access.can_edit_files:
        raise forbidden("Only the owner and editors can add files")
    require_not_archived(access)
    return await store_file(
        db,
        settings,
        workspace_id=access.workspace.id,
        chunks=chunks,
        original_name=original_name,
        original_path=original_path,
        content_type=content_type,
        actor=access.user,
    )


async def list_files(db: AsyncSession, access: WorkspaceAccess) -> list[WorkspaceFile]:
    require_inside(access)
    query = (
        select(WorkspaceFile)
        .where(WorkspaceFile.workspace_id == access.workspace.id)
        .order_by(WorkspaceFile.original_name, WorkspaceFile.id)
    )
    return list(await db.scalars(query))


async def get_file(db: AsyncSession, access: WorkspaceAccess, file_id: int) -> WorkspaceFile:
    require_inside(access)
    file = await db.get(WorkspaceFile, file_id)
    if file is None or file.workspace_id != access.workspace.id:
        raise file_not_found(file_id)
    return file


async def remove_file(
    db: AsyncSession, settings: Settings, access: WorkspaceAccess, file_id: int
) -> None:
    if not access.can_edit_files:
        raise forbidden("Only the owner and editors can remove files")
    require_not_archived(access)
    file = await get_file(db, access, file_id)
    path = file_path(settings, file)
    await db.delete(file)
    activity.record(
        db,
        "file_removed",
        actor=access.user,
        workspace_id=access.workspace.id,
        target_type="file",
        target_id=file.id,
        target_label=file.original_name,
    )
    await db.commit()
    # Delete from disk only after the commit: a failed commit keeps both.
    path.unlink(missing_ok=True)


def remove_workspace_folder(settings: Settings, workspace_id: int) -> None:
    """After a workspace is deleted (its rows went with CASCADE)."""
    shutil.rmtree(workspace_dir(settings, workspace_id).parent, ignore_errors=True)


async def chunks_of(path: Path) -> AsyncIterator[bytes]:
    """Read a file on the server in chunks (for the CLI)."""
    with path.open("rb") as source:
        while chunk := await asyncio.to_thread(source.read, CHUNK_SIZE):
            yield chunk
