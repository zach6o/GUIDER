"""Capability-based provider lookup.

Callers ask for a role and get an adapter. They MUST NOT compare provider ids:
that comparison exists only here and inside an adapter module, so adding a
provider stays a one-file change (ADR-017).
"""

from collections.abc import Callable
from typing import Any

from app.errors import GuideError
from app.providers.base import CapabilityDescriptor, Role
from app.providers.fixture import FixtureProvider
from app.providers.openai import OpenAIVision

FIXTURE = CapabilityDescriptor(
    id="fixture",
    display_name="Deterministic fixture",
    roles=frozenset({"analyze"}),
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
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[CapabilityDescriptor, Callable[..., Any]]] = {}

    def register(
        self, descriptor: CapabilityDescriptor, factory: Callable[..., Any]
    ) -> None:
        self._entries[descriptor.id] = (descriptor, factory)

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


def default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FIXTURE, FixtureProvider)
    registry.register(OPENAI, OpenAIVision)
    return registry


registry = default_registry()
