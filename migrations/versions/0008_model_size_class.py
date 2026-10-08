"""model size class

models: size_class (how big a step the model handles, and whether it
thinks), reasoning_tokens (room for thinking), max_output_tokens (the
model's own output cap). drafts/token_budgets.md, phase 2. Also sets the
class of the models already in the catalog, by name.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIZE_CLASSES = ("small", "medium", "large", "small_think", "medium_think", "large_think")

# The test server's catalog on 2026-10-08. Other models stay 'small'.
CLASSES = {
    "medium": ("qwen2.5:7b", "llama3.1:8b", "qwen2.5-coder:7b"),
    "large": ("qwen2.5:14b", "qwen2.5-coder:14b", "mistral-small:22b"),
    "medium_think": ("deepseek-r1:7b",),
}


def upgrade() -> None:
    """Upgrade schema."""
    size_class = postgresql.ENUM(*SIZE_CLASSES, name="model_size_class")
    size_class.create(op.get_bind())
    op.add_column(
        "models",
        sa.Column("size_class", size_class, server_default="small", nullable=False),
    )
    op.add_column("models", sa.Column("reasoning_tokens", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("max_output_tokens", sa.Integer(), nullable=True))
    op.create_check_constraint("models_reasoning_tokens_check", "models", "reasoning_tokens > 0")
    op.create_check_constraint("models_max_output_tokens_check", "models", "max_output_tokens > 0")
    for size, names in CLASSES.items():
        op.execute(
            sa.text(
                "UPDATE models SET size_class = CAST(:size AS model_size_class) WHERE name = ANY(:names)"
            ).bindparams(size=size, names=list(names))
        )
    # A thinking model works now: its class gives it room to think.
    op.execute("UPDATE models SET available = true WHERE name = 'deepseek-r1:7b'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("models_max_output_tokens_check", "models", type_="check")
    op.drop_constraint("models_reasoning_tokens_check", "models", type_="check")
    op.drop_column("models", "max_output_tokens")
    op.drop_column("models", "reasoning_tokens")
    op.drop_column("models", "size_class")
    op.execute("DROP TYPE model_size_class")
