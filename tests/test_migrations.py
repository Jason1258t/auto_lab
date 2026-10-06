"""The migrations and the ORM models must describe the same schema.

Runs against TEST_DATABASE_URL (the autolab_test database from
compose.yaml). The test drops everything in that database first.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from autolab.config import get_settings
from autolab.db.models import Base


@pytest.fixture(scope="module")
def test_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


@pytest.fixture(scope="module")
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


def schema_diff(url: str) -> list:
    engine = create_engine(url)
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "compare_server_default": True}
        )
        diff = compare_metadata(context, Base.metadata)
    engine.dispose()
    return diff


def test_upgrade_matches_models(test_url: str, alembic_config: Config) -> None:
    reset_database(test_url)
    command.upgrade(alembic_config, "head")
    assert schema_diff(test_url) == []


def test_downgrade_and_upgrade_again(test_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert schema_diff(test_url) == []


def test_seed_data(test_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    engine = create_engine(test_url)
    with engine.connect() as conn:
        roles = conn.execute(text("SELECT name FROM roles ORDER BY name")).scalars().all()
    engine.dispose()
    assert roles == ["editor", "reviewer", "viewer"]
