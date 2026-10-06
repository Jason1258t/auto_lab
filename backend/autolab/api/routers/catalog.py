"""Catalog (models, pipelines) and admin routes."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from autolab.api.deps import AdminPrincipal, DbSession
from autolab.api.schemas.catalog import (
    ModelIn,
    ModelOut,
    ModelUpdate,
    PipelineOut,
    ProviderIn,
    ProviderOut,
    ProviderUpdate,
)
from autolab.api.schemas.workspaces import ActivityEventOut
from autolab.db.models import ActivityEvent, ModelProvider
from autolab.services import admins as admins_service
from autolab.services import catalog as catalog_service

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
