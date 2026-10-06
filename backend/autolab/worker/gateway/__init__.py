"""Adapters by name (`model_providers.adapter`)."""

from autolab.worker.gateway.base import (
    Adapter,
    GatewayError,
    GenerateRequest,
    GenerateResult,
    Message,
)
from autolab.worker.gateway.ollama import OllamaAdapter

__all__ = [
    "Adapter",
    "GatewayError",
    "GenerateRequest",
    "GenerateResult",
    "Message",
    "OllamaAdapter",
    "make_adapters",
]


def make_adapters(timeout_seconds: float) -> dict[str, Adapter]:
    """One adapter per name. 'openai_compatible' and 'anthropic' come later;
    a model with such a provider fails with a clear error until then."""
    return {"ollama": OllamaAdapter(timeout_seconds)}
