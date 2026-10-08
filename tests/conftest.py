"""Shared test setup.

Tests use the autolab_test database (TEST_DATABASE_URL). Each test runs
inside one transaction that is rolled back at the end, so tests never see
each other's data. Service commits only release a savepoint.
"""

import os

# Must be set before the settings are read for the first time.
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-0123456789"

from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, pool, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from autolab.api.app import create_app  # noqa: E402
from autolab.api.deps import get_session  # noqa: E402
from autolab.config import Settings, get_settings  # noqa: E402
from autolab.logstore import FileLogStore  # noqa: E402
from autolab_engine.kinds import research  # noqa: E402


@pytest.fixture(autouse=True)
def no_search_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry empty searches at once in tests (no 10 and 30 s pauses)."""
    monkeypatch.setattr(research, "SEARCH_RETRY_SECONDS", (0.0, 0.0))


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
def settings(tmp_path) -> Settings:
    """App settings with a temp data folder, so tests never write into
    the real data/. Tests may change fields (e.g. max_upload_bytes)."""
    return get_settings().model_copy(
        update={
            "data_dir": str(tmp_path / "data"),
            "uploaded_pipelines_dir": str(tmp_path / "data" / "pipelines"),
        }
    )


@pytest.fixture
async def client(db: AsyncSession, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = same_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.log_store = FileLogStore(Path(settings.data_dir) / "logs")
    # https: the refresh cookie is Secure, so it is only sent over https.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


class ApiUser:
    """A signed-up and logged-in user for API tests."""

    def __init__(self, id: int, username: str, token: str) -> None:
        self.id = id
        self.username = username
        self.headers = {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_user(client: httpx.AsyncClient):
    async def make(username: str) -> ApiUser:
        email = f"{username}@example.com"
        password = "a long enough password"
        signup = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "username": username,
                "display_name": username.title(),
                "password": password,
            },
        )
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert signup.status_code == 201, signup.text
        return ApiUser(signup.json()["id"], username, login.json()["access_token"])

    return make


class Catalog:
    """Ids of a ready pipeline version and model, for task tests."""

    def __init__(self, pipeline_id: int, version_id: int, model_id: int) -> None:
        self.pipeline_id = pipeline_id
        self.version_id = version_id
        self.model_id = model_id


@pytest.fixture
async def catalog(db: AsyncSession) -> Catalog:
    """The seed has pipelines but no versions or models (the worker adds
    versions from the pipelines/ folder later), so tests add their own."""
    from sqlalchemy import select

    from autolab.db.models import Model, Pipeline, PipelineVersion

    pipeline_id = await db.scalar(select(Pipeline.id).where(Pipeline.name == "research"))
    version = PipelineVersion(
        pipeline_id=pipeline_id,
        version_name="1.0.0",
        version_code=1,
        file_path="pipelines/research/1.0.0.yaml",
        file_hash="test",
    )
    model = Model(provider_id=1, name="test-model", context_length=4096)
    db.add_all([version, model])
    await db.commit()
    return Catalog(pipeline_id, version.id, model.id)


@pytest.fixture
def session_factory(db: AsyncSession):
    """New sessions on the test connection, for code that opens its own
    sessions (the worker). Their commits are savepoints too."""

    def make() -> AsyncSession:
        return AsyncSession(
            bind=db.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

    return make
