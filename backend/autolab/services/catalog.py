"""Model catalog and pipelines: read for everyone, change for admins."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Model, ModelProvider, Pipeline, PipelineVersion
from autolab.errors import AppError


async def list_models(db: AsyncSession, include_unavailable: bool) -> list[Model]:
    query = select(Model).order_by(Model.name)
    if not include_unavailable:
        query = query.where(Model.available.is_(True))
    return list(await db.scalars(query))


async def list_pipelines(db: AsyncSession) -> list[tuple[Pipeline, PipelineVersion | None]]:
    """Each pipeline with its newest version (None if it has no version
    yet). New tasks always use the newest one."""
    newest = (
        select(PipelineVersion.pipeline_id, func.max(PipelineVersion.version_code).label("code"))
        .group_by(PipelineVersion.pipeline_id)
        .subquery()
    )
    query = (
        select(Pipeline, PipelineVersion)
        .outerjoin(newest, newest.c.pipeline_id == Pipeline.id)
        .outerjoin(
            PipelineVersion,
            (PipelineVersion.pipeline_id == Pipeline.id)
            & (PipelineVersion.version_code == newest.c.code),
        )
        .order_by(Pipeline.name)
    )
    return [(pipeline, version) for pipeline, version in await db.execute(query)]


async def _save(db: AsyncSession, obj, conflict_code: str, conflict_message: str):
    """Commit and turn a unique-constraint error into a 409."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, conflict_code, conflict_message) from exc
    await db.commit()
    await db.refresh(obj)
    return obj


async def create_provider(db: AsyncSession, **fields) -> ModelProvider:
    provider = ModelProvider(**fields)
    db.add(provider)
    return await _save(db, provider, "provider_exists", f"Provider {fields['name']} exists")


async def update_provider(db: AsyncSession, provider_id: int, changes: dict) -> ModelProvider:
    provider = await db.get(ModelProvider, provider_id)
    if provider is None:
        raise AppError(404, "provider_not_found", f"Provider {provider_id} not found")
    for field, value in changes.items():
        setattr(provider, field, value)
    return await _save(db, provider, "provider_exists", "A provider with this name exists")


async def create_model(db: AsyncSession, **fields) -> Model:
    if await db.get(ModelProvider, fields["provider_id"]) is None:
        raise AppError(404, "provider_not_found", f"Provider {fields['provider_id']} not found")
    model = Model(**fields)
    db.add(model)
    return await _save(db, model, "model_exists", "This provider already has this model")


async def update_model(db: AsyncSession, model_id: int, changes: dict) -> Model:
    """Models are never deleted; set available = false instead."""
    model = await db.get(Model, model_id)
    if model is None:
        raise AppError(404, "model_not_found", f"Model {model_id} not found")
    for field, value in changes.items():
        setattr(model, field, value)
    return await _save(db, model, "model_exists", "This provider already has this model")
