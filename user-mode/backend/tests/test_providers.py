import pytest

from app.errors import GuideError
from app.providers.base import CapabilityDescriptor, Guidance
from app.providers.fixture import FixtureProvider
from app.providers.openai import OpenAIVision
from app.providers.registry import ProviderRegistry, default_registry
from app.providers.schema import render, strict_schema

LOCAL = CapabilityDescriptor(
    id="local-double",
    display_name="Local double",
    roles=frozenset({"analyze"}),
    vision=False,
    structured_output="none",
    max_image_px=1024,
    cost_tier="cheap",
    byok_only=False,
    local=True,
)
REMOTE = CapabilityDescriptor(
    id="remote-double",
    display_name="Remote double",
    roles=frozenset({"analyze", "guide"}),
    vision=True,
    structured_output="json_schema",
    max_image_px=2560,
    cost_tier="capable",
    byok_only=True,
    local=False,
)


def test_default_registry_selects_adapters_by_role():
    registry = default_registry()
    assert isinstance(registry.select("analyze"), FixtureProvider)
    assert isinstance(registry.select("guide"), OpenAIVision)


def test_unsatisfiable_role_fails_closed_without_naming_a_provider():
    with pytest.raises(GuideError) as error:
        default_registry().select("plan")
    assert error.value.status == 503
    assert error.value.body["code"] == "dependency_unavailable"
    assert "plan" not in error.value.body["message"]


def test_selection_orders_on_capability_not_registration_name():
    registry = ProviderRegistry()
    registry.register(REMOTE, lambda: "remote")
    registry.register(LOCAL, lambda: "local")
    assert registry.select("analyze", local_only=True) == "local"
    assert {d.id for d in registry.for_role("guide")} == {"remote-double"}


def test_local_only_has_no_remote_fallback():
    registry = ProviderRegistry()
    registry.register(REMOTE, lambda: "remote")
    with pytest.raises(GuideError):
        registry.select("guide", local_only=True)


def test_build_rejects_a_provider_that_lacks_the_requested_role():
    registry = ProviderRegistry()
    registry.register(LOCAL, lambda: "local")
    with pytest.raises(GuideError):
        registry.build("local-double", "guide")


def test_strict_schema_drops_only_the_unsupported_bounds():
    schema = strict_schema(Guidance)
    observation = schema["properties"]["observation"]
    assert "minLength" not in observation and "maxLength" not in observation
    assert observation["type"] == "string"
    assert schema["properties"]["disposition"]["enum"] == ["guide", "needs_context", "blocked"]
    # Bounds remain enforced on the way in, so dropping them cannot widen input.
    assert Guidance.model_fields["observation"].metadata


def test_render_emits_a_strict_named_json_schema_block():
    block = render(Guidance, "guider_step", "json_schema")["format"]
    assert block["type"] == "json_schema"
    assert block["name"] == "guider_step"
    assert block["strict"] is True
    assert block["schema"]["properties"].keys() == Guidance.model_fields.keys()


def test_unimplemented_dialect_raises_instead_of_emitting_an_ignored_format():
    with pytest.raises(NotImplementedError):
        render(Guidance, "guider_step", "tool")


def test_compatibility_shims_still_resolve():
    from app import cloud, provider

    assert provider.FixtureProvider is FixtureProvider
    assert cloud.OpenAIVision is OpenAIVision
    assert cloud.Guidance is Guidance
