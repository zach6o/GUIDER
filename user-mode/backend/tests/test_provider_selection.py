from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.errors import GuideError
from app.main import create_app
from app.providers.analysis import SavedAnalysis
from app.providers.anthropic import AnthropicClaude
from app.providers.compatible import Ollama
from app.providers.registry import default_registry
from tests.test_compatible import CONTEXT, answer, context_request, transport
from tests.test_provider_matrix import claude


def test_configured_engine_uses_real_adapters_for_every_role():
    settings = Settings(provider_id="anthropic", provider_api_key=SecretStr("test-only"))
    registry = default_registry(settings)
    for role in ("plan", "instruct", "observe", "observe_context", "import"):
        assert isinstance(registry.select(role), AnthropicClaude)
    assert isinstance(registry.select("analyze"), SavedAnalysis)


def test_local_provider_needs_no_dummy_key():
    registry = default_registry(Settings(provider_id="ollama"))
    assert isinstance(registry.select("plan"), Ollama)


@pytest.mark.parametrize(
    "values",
    [
        {"provider_id": "unknown"},
        {"provider_id": "anthropic"},
        {"provider_api_key": SecretStr("test-only")},
    ],
)
def test_incomplete_configuration_never_looks_like_a_working_fixture(values):
    with pytest.raises(GuideError):
        default_registry(Settings(**values))


async def test_real_context_adapter_sends_the_frame_and_validates_the_answer():
    seen = []
    provider = AnthropicClaude(api_key=SecretStr("test-only"), transport=claude(CONTEXT, seen=seen))
    result = await provider.observe_context(context_request(), b"synthetic")
    assert result.controls[0].label == "Run"
    assert len(seen) == 1


@pytest.mark.parametrize("kind", ["native", "compatible"])
async def test_saved_analysis_keeps_identifiers_out_of_the_model(kind):
    result = {
        "observations": [],
        "explanation": "A shell prompt is visible.",
        "needs_context": False,
        "context_request": None,
    }
    seen = []
    adapter = (
        AnthropicClaude(api_key=SecretStr("test-only"), transport=claude(result, seen=seen))
        if kind == "native"
        else Ollama(transport=transport(answer(result), capture=seen))
    )
    identifiers = [str(uuid4()), str(uuid4())]
    analysis = await SavedAnalysis(adapter).analyze(
        [(value, b"synthetic") for value in identifiers]
    )
    assert [str(value) for value in analysis.screenshot_ids] == identifiers
    assert analysis.explanation == result["explanation"]
    assert all(value not in seen[0].content.decode() for value in identifiers)


async def test_app_wiring_uses_the_configured_observer():
    app = create_app(Settings(provider_id="ollama"), start_worker=False)
    assert isinstance(app.state.observer, Ollama)
    assert isinstance(app.state.provider, SavedAnalysis)
    await app.state.engine.dispose()
