"""Request and response bodies for models, providers and pipelines."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Adapter = Literal["ollama", "openai_compatible", "anthropic"]


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    adapter: Adapter
    base_url: str | None = None
    secret_id: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    adapter: Adapter | None = None
    base_url: str | None = None
    secret_id: str | None = None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    adapter: str
    base_url: str | None
    # secret_id is not shown: it only matters to the worker.


class ModelIn(BaseModel):
    provider_id: int
    name: str = Field(min_length=1, max_length=200)
    base_url: str | None = None
    context_length: int = Field(gt=0)
    vram_mb: int | None = Field(default=None, ge=0)
    ram_mb: int | None = Field(default=None, ge=0)
    cost_per_1m_input: Decimal | None = Field(default=None, ge=0)
    cost_per_1m_output: Decimal | None = Field(default=None, ge=0)
    description: str | None = None


class ModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = None
    context_length: int | None = Field(default=None, gt=0)
    vram_mb: int | None = Field(default=None, ge=0)
    ram_mb: int | None = Field(default=None, ge=0)
    cost_per_1m_input: Decimal | None = Field(default=None, ge=0)
    cost_per_1m_output: Decimal | None = Field(default=None, ge=0)
    description: str | None = None
    available: bool | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    name: str
    context_length: int
    vram_mb: int | None
    ram_mb: int | None
    cost_per_1m_input: Decimal | None
    cost_per_1m_output: Decimal | None
    description: str | None
    available: bool
    created_at: datetime


class PipelineOut(BaseModel):
    id: int
    name: str
    description: str | None
    # Newest version; None = the pipeline has no version file yet, so no
    # task can use it.
    version_id: int | None
    version_name: str | None
