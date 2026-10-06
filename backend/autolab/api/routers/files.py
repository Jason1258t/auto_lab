"""Workspace files: upload, list, download, remove."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Form, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from autolab.api.deps import CurrentPrincipal, DbSession, SettingsDep
from autolab.services import files as files_service
from autolab.services.permissions import load_access

router = APIRouter(prefix="/workspaces/{workspace_id}/files", tags=["files"])


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    original_path: str | None
    file_name: str  # current name in the workspace folder
    size_bytes: int
    sha256: str
    content_type: str | None
    uploaded_by: int | None
    created_at: datetime


async def _chunks(upload: UploadFile):
    while chunk := await upload.read(files_service.CHUNK_SIZE):
        yield chunk


@router.get("")
async def list_files(
    workspace_id: int, principal: CurrentPrincipal, db: DbSession
) -> list[FileOut]:
    access = await load_access(db, workspace_id, principal.user)
    return [FileOut.model_validate(f) for f in await files_service.list_files(db, access)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(
    workspace_id: int,
    file: UploadFile,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: SettingsDep,
    # Where the file was on the user's side, e.g. "course/week 1/notes.md"
    # (a folder upload sends it). Only stored, never used as a path here.
    original_path: Annotated[str | None, Form(max_length=1000)] = None,
) -> FileOut:
    access = await load_access(db, workspace_id, principal.user)
    stored = await files_service.add_file(
        db,
        settings,
        access,
        chunks=_chunks(file),
        original_name=file.filename or "file",
        original_path=original_path,
        content_type=file.content_type,
    )
    return FileOut.model_validate(stored)


@router.get("/{file_id}/download")
async def download_file(
    workspace_id: int,
    file_id: int,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: SettingsDep,
) -> FileResponse:
    access = await load_access(db, workspace_id, principal.user)
    file = await files_service.get_file(db, access, file_id)
    return FileResponse(
        files_service.file_path(settings, file),
        filename=file.original_name,
        media_type=file.content_type or "application/octet-stream",
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_file(
    workspace_id: int,
    file_id: int,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: SettingsDep,
) -> None:
    access = await load_access(db, workspace_id, principal.user)
    await files_service.remove_file(db, settings, access, file_id)
