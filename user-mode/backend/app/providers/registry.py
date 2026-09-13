"""Capability-based provider lookup.

Callers ask for a role and get an adapter. They MUST NOT compare provider ids:
that comparison exists only here and inside an adapter module, so adding a
provider stays a one-file change (ADR-017).
"""

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from app.errors import GuideError
from app.providers.anthropic import MODELS as CLAUDE_MODELS
from app.providers.anthropic import AnthropicClaude
from app.providers.base import CapabilityDescriptor, Role
from app.providers.fixture import FixtureProvider
from app.providers.openai import MODELS as OPENAI_MODELS
from app.providers.openai import OpenAIVision

if TYPE_CHECKING:  # a registry that imported Settings at runtime would invert
    from app.config import Settings  # the dependency between config and providers

FIXTURE = CapabilityDescriptor(
    id="fixture",
    display_name="Deterministic fixture",
    roles=frozenset({"analyze", "plan", "instruct", "observe"}),
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
    roles=frozenset({"guide", "observe", "plan", "instruct"}),
    vision=True,
    structured_output="native",
    max_image_px=2560,
    cost_tier="capable",
    byok_only=False,
    local=False,
    models=CLAUDE_MODELS,
    default_model=CLAUDE_MODELS[0],
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[CapabilityDescriptor, Callable[..., Any]]] = {}

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
        return entry[1](**kwargs)

    def select(self, role: Role, *, local_only: bool = False, **kwargs: Any) -> Any:
        """First adapter satisfying `role`. `local_only` keeps work off the network."""
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
    """Fixture first, always. A configured provider is registered after it, so
    every role still resolves with no credentials and no network, and adding one
    changes which adapter answers rather than whether anything does.

    Ordering is the whole selection rule: `select` takes the first adapter that
    satisfies the role, so the fixture keeps serving the engine roles until a
    deployment deliberately prefers something else.
    """
    registry = ProviderRegistry()
    registry.register(FIXTURE, FixtureProvider)
    registry.register(OPENAI, OpenAIVision)
    if settings is not None and settings.provider_api_key is not None:
        configured = {ANTHROPIC.id: AnthropicClaude}.get(settings.provider_id)
        if configured is None:
            raise GuideError(
                503,
                "dependency_unavailable",
                "No provider is configured for this capability.",
            )
        descriptor = ANTHROPIC
        registry.register(
            descriptor,
            partial(
                configured,
                api_key=settings.provider_api_key,
                model=descriptor.model_or_default(settings.provider_model),
            ),
        )
    return registry


# The credential-free default. `create_app` replaces it with one built from its
# own Settings, so nothing here reads configuration at import time.
registry = default_registry()
