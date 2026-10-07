"""deep research and code pipelines

New rows in pipelines (data only, no schema change):
- deep_research: long research in rounds (pipelines/deep_research/).
- code: one small program, checked by static analysis.
- python_cli: a Python command-line tool, planned and checked step by step.

The worker syncs their version files; a row without a file is allowed
(like opinion_survey).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PIPELINES = (
    ("deep_research", "Long research in rounds, many sources, every claim with a quote"),
    ("code", "One small program, written and checked by static analysis"),
    ("python_cli", "Python command-line tool, planned and checked step by step"),
)


def upgrade() -> None:
    """Upgrade schema."""
    pipelines = sa.table("pipelines", sa.column("name", sa.Text), sa.column("description", sa.Text))
    op.bulk_insert(pipelines, [{"name": n, "description": d} for n, d in PIPELINES])


def downgrade() -> None:
    """Downgrade schema."""
    # Fails (RESTRICT) if versions of these pipelines exist: that is wanted,
    # tasks may use them.
    names = ", ".join(f"'{n}'" for n, _ in PIPELINES)
    op.execute(f"DELETE FROM pipelines WHERE name IN ({names})")
