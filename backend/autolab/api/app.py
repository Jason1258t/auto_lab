"""The FastAPI app. Run: uv run uvicorn autolab.api.app:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from autolab.api.routers import (
    auth,
    catalog,
    files,
    me,
    publications,
    results,
    tasks,
    workspaces,
)
from autolab.config import get_settings
from autolab.db.engine import make_engine, make_session_factory
from autolab.errors import install_error_handlers
from autolab.logstore import make_log_store

MIN_JWT_SECRET_LENGTH = 32


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")
    engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(engine)
    app.state.log_store = make_log_store(settings)  # GET /calls/{id}/log
    yield
    await engine.dispose()
    if hasattr(app.state.log_store, "close"):
        await app.state.log_store.close()


def create_app() -> FastAPI:
    app = FastAPI(title="AutoLab", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,  # the refresh cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for router in (
        auth.router,
        me.router,
        workspaces.router,
        files.router,
        tasks.router,
        results.router,
        publications.router,
        publications.admin_router,
        catalog.router,
        catalog.admin_router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
