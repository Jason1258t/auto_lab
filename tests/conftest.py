"""Shared test setup.

Tests use the autolab_test database (TEST_DATABASE_URL). Each test runs
inside one transaction that is rolled back at the end, so tests never see
each other's data. Service commits only release a savepoint.
"""

import os

# Must be set before the settings are read for the first time.
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-0123456789"

from collections.abc import AsyncIterator  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, pool, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from autolab.api.app import create_app  # noqa: E402
from autolab.api.deps import get_session  # noqa: E402
from autolab.config import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def test_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


@pytest.fixture(scope="session")
def alembic_config(test_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_url)
    config.attributes["configure_logger"] = False
    return config


def reset_database(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_db(test_url: str, alembic_config: Config) -> str:
    """A clean test database at the newest migration, once per test run."""
    reset_database(test_url)
    command.upgrade(alembic_config, "head")
    return test_url


@pytest.fixture
async def db(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            # session.commit() only releases a savepoint; the outer
            # transaction is rolled back below.
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def client(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = same_session
    # https: the refresh cookie is Secure, so it is only sent over https.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client
