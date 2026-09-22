"""Capability-based provider lookup.

Callers ask for a role and get an adapter. They MUST NOT compare provider ids:
that comparison exists only here and inside an adapter module, so adding a
provider stays a one-file change (ADR-017).
"""

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Any

from app.errors import GuideError
from app.providers.analysis import SavedAnalysis
from app.providers.anthropic import MODELS as CLAUDE_MODELS
from app.providers.anthropic import AnthropicClaude
from app.providers.base import CapabilityDescriptor, Role
from app.providers.compatible import DeepSeek, Groq, LMStudio, Ollama, OpenRouter
from app.providers.fixture import FixtureProvider
from app.providers.openai import MODELS as OPENAI_MODELS
from app.providers.openai import OpenAIVision

if TYPE_CHECKING:  # a registry that imported Settings at runtime would invert
    from app.config import Settings  # the dependency between config and providers

FIXTURE = CapabilityDescriptor(
    id="fixture",
    display_name="Deterministic fixture",
    roles=frozenset({"analyze", "plan", "instruct", "observe", "observe_context", "import"}),
    vision=False,
    structured_output="none",
    max_image_px=8192,
    cost_tier="cheap",
    byok_only=False,
    local=True,
)

OPENAI = CapabilityDescriptor(
    id="openai",
    display_name="OpenAI",
    roles=frozenset({"guide"}),
    vision=True,
    structured_output="json_schema",
    max_image_px=2560,
    cost_tier="standard",
    byok_only=True,
    local=False,
    models=OPENAI_MODELS,
    default_model=OPENAI_MODELS[0],
)


ANTHROPIC = CapabilityDescriptor(
    id="anthropic",
    display_name="Claude",
    roles=frozenset({
        "analyze", "guide", "observe", "observe_context", "plan", "instruct", "import",
    }),
    vision=True,
    structured_output="native",
    max_image_px=2560,
    cost_tier="capable",
    byok_only=False,
    local=False,
    models=CLAUDE_MODELS,
    default_model=CLAUDE_MODELS[0],
)


# Every service behind `app/providers/compatible.py`, described once. The
# adapter class is the only thing that knows a vendor's name; this table is what
# the registry selects on.
ENGINE_ROLES = frozenset({"analyze", "observe", "observe_context", "plan", "instruct", "import"})


def _compatible(adapter, cost: str, local: bool = False) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        id=adapter.__name__.lower(),
        display_name=adapter.name,
        roles=ENGINE_ROLES,
        vision=True,
        structured_output="json_schema",
        max_image_px=2560,
        cost_tier=cost,  # type: ignore[arg-type]
        byok_only=not local,
        local=local,
        models=adapter.models,
        default_model=adapter.models[0],
    )


COMPATIBLE: dict[str, tuple[CapabilityDescriptor, type]] = {
    adapter.__name__.lower(): (_compatible(adapter, cost, local), adapter)
    for adapter, cost, local in (
        (OpenRouter, "standard", False),
        (Groq, "cheap", False),
        (DeepSeek, "cheap", False),
        (Ollama, "cheap", True),
        (LMStudio, "cheap", True),
    )
}

CATALOG = {ANTHROPIC.id: (ANTHROPIC, AnthropicClaude), **COMPATIBLE}


def available(provider_id: str, role: Role) -> CapabilityDescriptor:
    entry = CATALOG.get(provider_id)
    if entry is None or not entry[0].supports(role):
        raise GuideError(422, "provider_unavailable", "Choose a provider supporting this role.")
    return entry[0]


def build_configured(provider_id: str, role: Role, **kwargs: Any) -> Any:
    available(provider_id, role)
    adapter = CATALOG[provider_id][1](**kwargs)
    return SavedAnalysis(adapter) if role == "analyze" else adapter


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[CapabilityDescriptor, Callable[..., Any]]] = {}
        self.preferred: str | None = None

    def register(
        self, descriptor: CapabilityDescriptor, factory: Callable[..., Any]
    ) -> None:
        self._entries[descriptor.id] = (descriptor, factory)

    def descriptor(self, provider_id: str, role: Role) -> CapabilityDescriptor:
        """The capabilities of one adapter, for a caller that was handed an id it
        did not choose - a stored connection, say. Unknown ids fail closed."""
        entry = self._entries.get(provider_id)
        if entry is None or not entry[0].supports(role):
            raise GuideError(
                503,
                "dependency_unavailable",
                "No provider is configured for this capability.",
            )
        return entry[0]

    def first_for(self, role: Role) -> CapabilityDescriptor:
        """The adapter a caller gets when it expresses no preference."""
        for descriptor in self.for_role(role):
            return descriptor
        raise GuideError(
            503,
            "dependency_unavailable",
            "No provider is configured for this capability.",
        )

    def describe(self) -> list[CapabilityDescriptor]:
        return [descriptor for descriptor, _ in self._entries.values()]

    def for_role(self, role: Role) -> list[CapabilityDescriptor]:
        return [d for d in self.describe() if d.supports(role)]

    def build(self, provider_id: str, role: Role, **kwargs: Any) -> Any:
        entry = self._entries.get(provider_id)
        if entry is None or not entry[0].supports(role):
            raise GuideError(
                503,
                "dependency_unavailable",
                "No provider is configured for this capability.",
            )
        adapter = entry[1](**kwargs)
        return SavedAnalysis(adapter) if role == "analyze" and hasattr(
            adapter, "analyze_images"
        ) else adapter

    def select(self, role: Role, *, local_only: bool = False, **kwargs: Any) -> Any:
        """Explicit configuration wins; unsupported roles fail without fallback."""
        if self.preferred and not local_only:
            return self.build(self.preferred, role, **kwargs)
        for descriptor in self.for_role(role):
            if local_only and not descriptor.local:
                continue
            return self.build(descriptor.id, role, **kwargs)
        raise GuideError(
            503,
            "dependency_unavailable",
            "No provider is configured for this capability.",
        )


def default_registry(settings: "Settings | None" = None) -> ProviderRegistry:
    """No configuration means fixture mode. Explicit configuration selects real work."""
    registry = ProviderRegistry()
    registry.register(FIXTURE, FixtureProvider)
    registry.register(OPENAI, OpenAIVision)
    # Personal connections supply their own key per call, without account setup.
    # Fixture stays first for unconfigured saved-task roles.
    registry.register(
        replace(ANTHROPIC, roles=frozenset({"guide"}), byok_only=True), AnthropicClaude
    )
    if settings is not None and (settings.provider_id or settings.provider_api_key):
        configured = {
            ANTHROPIC.id: AnthropicClaude,
            **{key: value[1] for key, value in COMPATIBLE.items()},
        }.get(settings.provider_id)
        if configured is None:
            raise GuideError(
                503,
                "dependency_unavailable",
                "No provider is configured for this capability.",
            )
        # The descriptor belongs to whichever adapter was configured, not to a
        # hardcoded one: registering Claude's capabilities for a Groq connection
        # would offer models that service has never heard of.
        descriptor = (
            ANTHROPIC
            if settings.provider_id == ANTHROPIC.id
            else COMPATIBLE[settings.provider_id][0]
        )
        if not descriptor.local and not settings.provider_api_key:
            raise GuideError(503, "dependency_unavailable", "The configured provider needs a key.")
        registry.register(
            descriptor,
            partial(
                configured,
                api_key=settings.provider_api_key,
                model=descriptor.model_or_default(settings.provider_model),
            ),
        )
        registry.preferred = descriptor.id
    return registry


# The credential-free default. `create_app` replaces it with one built from its
# own Settings, so nothing here reads configuration at import time.
registry = default_registry()
