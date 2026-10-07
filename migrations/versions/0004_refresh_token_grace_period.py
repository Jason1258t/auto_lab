"""refresh token grace period

sessions: previous_token_hash and rotated_at. After a refresh, the
previous refresh token still works for a few seconds (REFRESH_GRACE_SECONDS).
Reason: a page reload while a refresh is in flight sends the old cookie
again; without a grace period that ends the session (reuse detection).
Both columns are NULL until the first refresh, and set together.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sessions", sa.Column("previous_token_hash", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "sessions_previous_token_check",
        "sessions",
        "(previous_token_hash IS NULL) = (rotated_at IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("sessions_previous_token_check", "sessions", type_="check")
    op.drop_column("sessions", "rotated_at")
    op.drop_column("sessions", "previous_token_hash")
