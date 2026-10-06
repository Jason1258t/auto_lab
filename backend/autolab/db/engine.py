"""Async engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from autolab.config import get_settings


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or get_settings().database_url)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    # expire_on_commit=False: objects stay readable after commit, without
    # a new query (a lazy query would fail in async code).
    return async_sessionmaker(engine, expire_on_commit=False)
