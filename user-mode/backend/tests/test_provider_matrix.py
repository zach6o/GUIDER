"""Every adapter, the same fixtures, the same rules.

ADR-017's claim is that a role is a contract and a provider is an implementation
detail. This file is the test of that claim: identical inputs go through every
adapter that serves a role, and each answer has to satisfy the same schema and
survive the same guard. A provider that needs special handling somewhere else in
the application has failed the abstraction, so the last test here reads the
source and says so.

No network. Remote adapters are exercised through an injected httpx transport
that answers with recorded shapes; no key in this file is real.
"""

import json
import pathlib

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.errors import GuideError
from app.guide.guard import step_policy, vet_guidance, vet_instruction, vet_observation
from app.providers.anthropic import DEFAULT_MODEL, AnthropicClaude
from app.providers.base import (
    CheckInput,
    InstructionContext,
    ObserveContext,
    ObserveResult,
    PlanContext,
    ProposedInstruction,
    ProposedPlan,
)
from app.providers.fixture import FixtureProvider
from app.providers.registry import ANTHROPIC, default_registry
from app.providers.schema import closed_schema, render

KEY = SecretStr("sk-ant-not-a-real-key")

PLAN_CONTEXT = PlanContext(
    goal="Work out why my script will not run",
    category="debug",
    application_key="powershell",
)
INSTRUCTION_CONTEXT = InstructionContext(
    goal="Work out why my script will not run",
    application_key="powershell",
    title="Open the terminal",
    action="Open the integrated terminal in your editor.",
    expected_result="A shell prompt appears in a panel.",
    fallback="Use the View menu, then Terminal.",
    explanation="The interpreter reports what went wrong in the terminal.",
    ordinal=1,
    total_steps=3,
)
OBSERVE_CONTEXT = ObserveContext(
    success_criterion="A command prompt is visible and accepts typing.",
    expected_result="A shell prompt appears in a panel.",
    application_key="powershell",
)

ANSWERS = {
    "plan": {
        "assumptions": ["Written from the goal alone."],
        "steps": [
            {
                "title": "Open the terminal",
                "action": "Open the integrated terminal.",
                "expected_result": "A prompt appears.",
                "success_criterion": "A prompt accepts typing.",
                "fallback": "Use the View menu.",
                "explanation": "Errors are printed there.",
                "application_key": "powershell",
                "risk": "low",
                "evidence_kind": "visual",
                "required": True,
            }
        ],
    },
    "instruct": {
        "what": "Open the integrated terminal.",
        "where": "In the editor, at the bottom.",
        "why": "The error is printed there.",
        "confirmation_hint": "A prompt appears.",
        "cannot_find_hint": "Use the View menu, then Terminal.",
    },
    "observe": {
        "step_complete": True,
        "confidence": 0.91,
        "app_visible": "powershell",
        "ui_changed": True,
        "anomaly": "none",
        "note": "A shell prompt is visible.",
    },
    "guide": {
        "observation": "The terminal cannot find the requests package.",
        "next_step": "Check which interpreter this terminal uses.",
        "where": "In the terminal panel.",
        "check_for": "A path printed below the command.",
        "question": "",
        "disposition": "guide",
    },
}


def claude(answer: dict, *, stop_reason: str = "end_turn", status: int = 200, seen=None):
    """An Anthropic transport that replays one recorded answer."""

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                status,
                json={
                    "content": [{"type": "text", "text": json.dumps(answer)}],
                    "stop_reason": stop_reason,
                },
            )
        return httpx.Response(status, json={"id": "model"})

    return httpx.MockTransport(handle)


def adapter(answer: dict, **kwargs) -> AnthropicClaude:
    return AnthropicClaude(api_key=KEY, transport=claude(answer, **kwargs))


# --- the same role, through every adapter that serves it -----------------


async def test_every_planner_returns_a_plan_the_guard_accepts():
    planners = [FixtureProvider(), adapter(ANSWERS["plan"])]
    for provider in planners:
        proposal = await provider.plan(PLAN_CONTEXT)
        assert isinstance(proposal, ProposedPlan)
        assert 1 <= len(proposal.steps) <= 12
        assert all(step.title and step.success_criterion for step in proposal.steps)
        # The guard's verdict is what gets persisted, whoever proposed the step.
        for step in proposal.steps:
            disposition, risk = step_policy(step)
            assert disposition in {"allow", "confirm", "block"}
            assert risk in {"low", "medium", "high"}


async def test_every_instruction_writer_returns_one_action_the_guard_accepts():
    writers = [FixtureProvider(), adapter(ANSWERS["instruct"])]
    for provider in writers:
        proposal = await provider.instruct(INSTRUCTION_CONTEXT)
        assert isinstance(proposal, ProposedInstruction)
        vetted = vet_instruction(proposal)
        assert vetted.what
        assert vetted.confirmation_hint


async def test_every_observer_answers_one_question_and_writes_no_guidance():
    observers = [FixtureProvider(), adapter(ANSWERS["observe"])]
    for provider in observers:
        result = await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")
        assert isinstance(result, ObserveResult)
        vetted = vet_observation(result)
        assert 0 <= vetted.confidence <= 1
        # There is nowhere for an instruction to go, whoever answered.
        assert not hasattr(vetted, "next_step")


async def test_every_guide_adapter_takes_its_key_per_call():
    seen: list[httpx.Request] = []
    provider = AnthropicClaude(transport=claude(ANSWERS["guide"], seen=seen))
    body = CheckInput(
        goal="Help me run my app",
        question="What now?",
        previous_step="",
        image_base64="unused-by-this-adapter",
        reviewed=True,
    )
    guidance = vet_guidance(await provider.analyze(KEY, DEFAULT_MODEL, body, b"frame-bytes"))
    assert guidance.disposition == "guide"
    # The credential came from the call, and the adapter holds none of its own.
    assert provider.api_key is None
    assert seen[0].headers["x-api-key"] == KEY.get_secret_value()


# --- what the adapter sends, and what it refuses to accept ---------------


async def test_the_frame_is_sent_as_an_image_block_with_the_schema_alongside():
    seen: list[httpx.Request] = []
    provider = AnthropicClaude(api_key=KEY, transport=claude(ANSWERS["observe"], seen=seen))
    await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")

    sent = json.loads(seen[0].content)
    kinds = [block["type"] for block in sent["messages"][0]["content"]]
    assert kinds == ["image", "text"]
    assert sent["messages"][0]["content"][0]["source"]["type"] == "base64"
    assert sent["model"] == DEFAULT_MODEL
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert seen[0].headers["anthropic-version"]
    # The success criterion is the observer's whole question; no history goes.
    assert json.loads(sent["messages"][0]["content"][1]["text"]) == OBSERVE_CONTEXT.model_dump()


async def test_a_declined_answer_is_reported_rather_than_guessed_at():
    provider = adapter(ANSWERS["observe"], stop_reason="refusal")
    with pytest.raises(GuideError) as error:
        await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")
    assert error.value.status == 503
    assert error.value.body["code"] == "answer_declined"


async def test_a_truncated_answer_is_not_treated_as_an_answer():
    provider = adapter(ANSWERS["observe"], stop_reason="max_tokens")
    with pytest.raises(GuideError) as error:
        await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")
    assert error.value.body["code"] == "incomplete_answer"


async def test_an_answer_outside_the_schema_is_refused():
    provider = adapter({"step_complete": True, "confidence": 4.2})
    with pytest.raises(GuideError) as error:
        await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")
    assert error.value.body["code"] == "invalid_answer"


async def test_a_rejected_key_is_reported_without_a_verdict():
    provider = adapter(ANSWERS["observe"], status=401)
    with pytest.raises(GuideError) as error:
        await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")
    assert error.value.status == 401


async def test_an_engine_role_without_a_credential_fails_closed():
    provider = AnthropicClaude(transport=claude(ANSWERS["observe"]))
    with pytest.raises(GuideError) as error:
        await provider.observe(OBSERVE_CONTEXT, b"frame-bytes")
    assert error.value.body["code"] == "dependency_unavailable"


# --- registration --------------------------------------------------------


def test_personal_keys_need_no_saved_account_provider_configuration():
    registry = default_registry(Settings(environment="test"))
    assert {descriptor.id for descriptor in registry.for_role("guide")} == {"openai", "anthropic"}
    assert isinstance(registry.build("anthropic", "guide"), AnthropicClaude)
    with pytest.raises(GuideError):
        registry.build("anthropic", "observe")
    assert isinstance(registry.select("observe"), FixtureProvider)


def test_a_configured_provider_serves_the_roles_it_declares():
    configured = Settings(
        environment="test", provider_id=ANTHROPIC.id, provider_api_key=KEY
    )
    registry = default_registry(configured)
    assert isinstance(registry.select("observe"), AnthropicClaude)
    assert isinstance(registry.build(ANTHROPIC.id, "observe"), AnthropicClaude)
    assert ANTHROPIC.supports("plan") and ANTHROPIC.supports("guide")
    with pytest.raises(GuideError):
        registry.build(ANTHROPIC.id, "verify")  # a role it does not declare


def test_the_rendered_schema_is_the_same_one_for_every_dialect():
    native = render(ObserveResult, "observation", "native")["format"]["schema"]
    json_schema = render(ObserveResult, "observation", "json_schema")["format"]["schema"]
    assert native["properties"] == json_schema["properties"]
    assert closed_schema(ObserveResult)["additionalProperties"] is False


# --- the gate ------------------------------------------------------------

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "app"

# What the gate is actually about: code that behaves differently depending on
# which provider answered. Adapter classes, adapter modules and model names are
# how that leaks in, so those are forbidden outside `app/providers/`.
DISPATCH = (
    "OpenAIVision",
    "AnthropicClaude",
    "providers.openai",
    "providers.anthropic",
    "gpt-4",
    "claude-opus",
    "claude-sonnet",
    "claude-haiku",
    "api.openai.com",
    "api.anthropic.com",
)

# Vendor words alone are not dispatch. `app/imports/` carries them as provenance
# the user chose - which assistant a pasted transcript came from, and the speaker
# labels inside it (ADR-018) - and that is data, not selection. Elsewhere they
# are allowed only on a line that is declaring that same provenance value.
VENDOR = ("openai", "anthropic", "chatgpt", "gemini", "claude")
PROVENANCE = ("imports",)
PROVENANCE_FIELD = ("source", "import_sources")


def sources() -> list[pathlib.Path]:
    return [
        path
        for path in sorted(BACKEND.rglob("*.py"))
        if "providers" not in path.parts and "__pycache__" not in path.parts
    ]


def lines_of(path: pathlib.Path) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if not line.lstrip().startswith("#")
    ]


def test_no_adapter_or_model_is_named_outside_the_providers_package():
    """The ADR-017 gate, read off the source.

    Anything outside `app/providers/` that names an adapter, an adapter module or
    a provider's model would make adding the next provider a change to that file
    too.
    """
    offenders = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sources()
        for number, line in lines_of(path)
        for name in DISPATCH
        if name.lower() in line.lower()
    ]
    assert offenders == []


def test_a_vendor_name_outside_the_providers_package_is_provenance_only():
    """Where a vendor is named at all, it is because the user said so.

    `app/imports/` reads speaker labels and records which assistant a transcript
    came from. Nothing else in the application may name one, in any form.
    """
    offenders = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sources()
        if not any(part in PROVENANCE for part in path.parts)
        for number, line in lines_of(path)
        for name in VENDOR
        if name in line.lower()
        and not any(field in line.lower() for field in PROVENANCE_FIELD)
    ]
    assert offenders == []
