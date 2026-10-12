"""rofl_article pipeline

New row in pipelines (data only, no schema change):
- rofl_article: a short funny article from a prompt (pipelines/rofl_article/).

The worker syncs its version files.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "rofl_article"
DESCRIPTION = "A short funny article from a prompt: a believable exaggeration of real details"


def upgrade() -> None:
    """Upgrade schema."""
    pipelines = sa.table("pipelines", sa.column("name", sa.Text), sa.column("description", sa.Text))
    op.bulk_insert(pipelines, [{"name": NAME, "description": DESCRIPTION}])


def downgrade() -> None:
    """Downgrade schema."""
    # Fails (RESTRICT) if versions of this pipeline exist: that is wanted,
    # tasks may use them.
    op.execute(f"DELETE FROM pipelines WHERE name = '{NAME}'")
