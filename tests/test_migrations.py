"""The migrations and the ORM models must describe the same schema.

Runs against TEST_DATABASE_URL (the autolab_test database from
compose.yaml). Fixtures `test_url` and `alembic_config`: tests/conftest.py.
The first test drops everything in that database.
"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from autolab.db.models import Base
from tests.conftest import reset_database


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
