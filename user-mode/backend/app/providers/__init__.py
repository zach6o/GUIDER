"""Provider adapters, selected by role and capability (ADR-017)."""

from app.providers.anthropic import AnthropicClaude
from app.providers.base import (
    MAX_IMAGE,
    MODEL,
    AnalysisProvider,
    CapabilityDescriptor,
    CheckInput,
    Guidance,
    LiveGuidanceProvider,
    Role,
    provider_error,
)
from app.providers.fixture import FixtureProvider, python_fixture
from app.providers.openai import POLICY, OpenAIVision
from app.providers.registry import ProviderRegistry, default_registry, registry

__all__ = [
    "MAX_IMAGE",
    "AnthropicClaude",
    "MODEL",
    "POLICY",
    "AnalysisProvider",
    "CapabilityDescriptor",
    "CheckInput",
    "FixtureProvider",
    "Guidance",
    "LiveGuidanceProvider",
    "OpenAIVision",
    "ProviderRegistry",
    "Role",
    "default_registry",
    "provider_error",
    "python_fixture",
    "registry",
]
