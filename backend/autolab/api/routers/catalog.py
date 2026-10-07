"""Catalog (models, pipelines) and admin routes."""

from typing import Annotated

from fastapi import APIRouter, Form, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from autolab.api.deps import AdminPrincipal, DbSession, SettingsDep
from autolab.api.schemas.catalog import (
    AdminPipelineOut,
    ModelIn,
    ModelOut,
    ModelUpdate,
    PipelineOut,
    PipelineUploadOut,
    PipelineVersionOut,
    ProviderIn,
    ProviderOut,
    ProviderUpdate,
)
from autolab.api.schemas.workspaces import ActivityEventOut
from autolab.db.models import ActivityEvent, ModelProvider
from autolab.services import admins as admins_service
from autolab.services import catalog as catalog_service
from autolab.services import pipelines as pipelines_service

router = APIRouter(tags=["catalog"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/models")
async def list_models(db: DbSession) -> list[ModelOut]:
    """Models a new task can use."""
    models = await catalog_service.list_models(db, include_unavailable=False)
    return [ModelOut.model_validate(m) for m in models]


@router.get("/pipelines")
async def list_pipelines(db: DbSession) -> list[PipelineOut]:
    return [
        PipelineOut(
            id=pipeline.id,
            name=pipeline.name,
            description=pipeline.description,
            version_id=version.id if version else None,
            version_name=version.version_name if version else None,
        )
        for pipeline, version in await catalog_service.list_pipelines(db)
    ]


# --- Admin ---


@admin_router.get("/models")
async def admin_list_models(_: AdminPrincipal, db: DbSession) -> list[ModelOut]:
    models = await catalog_service.list_models(db, include_unavailable=True)
    return [ModelOut.model_validate(m) for m in models]


@admin_router.post("/models", status_code=status.HTTP_201_CREATED)
async def create_model(body: ModelIn, _: AdminPrincipal, db: DbSession) -> ModelOut:
    return ModelOut.model_validate(await catalog_service.create_model(db, **body.model_dump()))


@admin_router.patch("/models/{model_id}")
async def update_model(
    model_id: int, body: ModelUpdate, _: AdminPrincipal, db: DbSession
) -> ModelOut:
    changes = body.model_dump(include=body.model_fields_set)
    return ModelOut.model_validate(await catalog_service.update_model(db, model_id, changes))


@admin_router.get("/model-providers")
async def list_providers(_: AdminPrincipal, db: DbSession) -> list[ProviderOut]:
    providers = await db.scalars(select(ModelProvider).order_by(ModelProvider.name))
    return [ProviderOut.model_validate(p) for p in providers]


@admin_router.post("/model-providers", status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderIn, _: AdminPrincipal, db: DbSession) -> ProviderOut:
    provider = await catalog_service.create_provider(db, **body.model_dump())
    return ProviderOut.model_validate(provider)


@admin_router.patch("/model-providers/{provider_id}")
async def update_provider(
    provider_id: int, body: ProviderUpdate, _: AdminPrincipal, db: DbSession
) -> ProviderOut:
    changes = body.model_dump(include=body.model_fields_set)
    provider = await catalog_service.update_provider(db, provider_id, changes)
    return ProviderOut.model_validate(provider)


@admin_router.post("/admins/{user_id}", status_code=status.HTTP_201_CREATED)
async def grant_admin(user_id: int, admin: AdminPrincipal, db: DbSession) -> None:
    await admins_service.grant_admin(db, user_id, granted_by=admin.user.username, actor=admin.user)


@admin_router.delete("/admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_admin(user_id: int, admin: AdminPrincipal, db: DbSession) -> None:
    await admins_service.revoke_admin(db, user_id, actor=admin.user)


@admin_router.get("/activity")
async def global_activity(
    _: AdminPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ActivityEventOut]:
    """Global events (workspace_id is NULL): admins, publishers, users."""
    events = await db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.workspace_id.is_(None))
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [ActivityEventOut.model_validate(e) for e in events]


# --- Admin: pipelines ---


@admin_router.get("/pipelines")
async def admin_list_pipelines(
    _: AdminPrincipal, db: DbSession, settings: SettingsDep
) -> list[AdminPipelineOut]:
    return [
        AdminPipelineOut(
            id=pipeline.id,
            name=pipeline.name,
            description=pipeline.description,
            versions=[
                PipelineVersionOut(
                    id=v.version.id,
                    version_name=v.version.version_name,
                    uploaded=v.uploaded,
                    tasks=v.tasks,
                    created_at=v.version.created_at,
                )
                for v in versions
            ],
        )
        for pipeline, versions in await pipelines_service.list_pipelines(db, settings)
    ]


@admin_router.get("/pipeline-versions/{version_id}/file", response_class=PlainTextResponse)
async def admin_pipeline_file(version_id: int, _: AdminPrincipal, db: DbSession) -> str:
    """The YAML text of a version."""
    return await pipelines_service.read_version_file(db, version_id)


@admin_router.post("/pipelines/upload", status_code=status.HTTP_201_CREATED)
async def admin_upload_pipeline(
    principal: AdminPrincipal,
    db: DbSession,
    settings: SettingsDep,
    file: UploadFile,
    name: Annotated[str, Form(max_length=50)],
    version: Annotated[str, Form(max_length=20)],
    dry_run: Annotated[bool, Form()] = False,
) -> PipelineUploadOut:
    """Upload a pipeline file: a new version, or a new pipeline if the name
    is new. dry_run=true only checks it. The name and version fields win
    over the file's own `pipeline:` and `version:` lines."""
    result = await pipelines_service.upload(
        db,
        settings,
        principal.user,
        name=name,
        version=version,
        content=await file.read(pipelines_service.MAX_FILE_BYTES + 1),
        dry_run=dry_run,
    )
    return PipelineUploadOut(
        pipeline_id=result.pipeline.id if result.pipeline.id is not None else 0,
        name=result.pipeline.name,
        version_id=result.version.id if result.version else None,
        version_name=version.strip(),
        created_pipeline=result.created_pipeline,
        saved=result.version is not None,
        notes=result.notes,
    )
