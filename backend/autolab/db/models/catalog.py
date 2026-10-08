"""Group 2: model catalog."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk, created_at, pg_enum, smallint_pk
from autolab.db.models.enums import CapabilityKind, ModelSizeClass


class ModelProvider(Base):
    """An admin can add a provider without a migration, if its adapter
    exists in code."""

    __tablename__ = "model_providers"

    id: Mapped[int] = smallint_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    # text + CHECK, not an enum: the list grows with every new adapter.
    adapter: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    secret_id: Mapped[str | None] = mapped_column(Text)  # no FK, external store

    __table_args__ = (
        CheckConstraint(
            "adapter IN ('ollama', 'openai_compatible', 'anthropic')",
            name="model_providers_adapter_check",
        ),
    )


class Model(Base):
    """One model from one provider = one row. Never deleted, only marked
    unavailable."""

    __tablename__ = "models"

    id: Mapped[int] = bigint_pk()
    provider_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("model_providers.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)  # NULL = provider's
    context_length: Mapped[int]
    vram_mb: Mapped[int | None]
    ram_mb: Mapped[int | None]
    cost_per_1m_input: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    cost_per_1m_output: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    description: Mapped[str | None] = mapped_column(Text)
    available: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = created_at()
    # Token budgets (drafts/token_budgets.md, phase 2).
    size_class: Mapped[ModelSizeClass] = mapped_column(
        pg_enum(ModelSizeClass, "model_size_class"), server_default="small"
    )
    reasoning_tokens: Mapped[int | None]  # NULL = 1024; *_think classes only
    max_output_tokens: Mapped[int | None]  # NULL = no own cap

    __table_args__ = (
        UniqueConstraint("provider_id", "name"),
        CheckConstraint("reasoning_tokens > 0", name="models_reasoning_tokens_check"),
        CheckConstraint("max_output_tokens > 0", name="models_max_output_tokens_check"),
        CheckConstraint("context_length > 0", name="models_context_length_check"),
        CheckConstraint("vram_mb >= 0", name="models_vram_mb_check"),
        CheckConstraint("ram_mb >= 0", name="models_ram_mb_check"),
        CheckConstraint("cost_per_1m_input >= 0", name="models_cost_per_1m_input_check"),
        CheckConstraint("cost_per_1m_output >= 0", name="models_cost_per_1m_output_check"),
    )


class Capability(Base):
    __tablename__ = "capabilities"

    id: Mapped[int] = smallint_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class ModelCapability(Base):
    __tablename__ = "model_capabilities"

    model_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("models.id", ondelete="CASCADE"), primary_key=True
    )
    capability_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("capabilities.id", ondelete="RESTRICT"), primary_key=True
    )
    kind: Mapped[CapabilityKind] = mapped_column(pg_enum(CapabilityKind, "capability_kind"))
    note: Mapped[str | None] = mapped_column(Text)
