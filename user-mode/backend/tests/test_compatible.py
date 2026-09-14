"""Five services, one adapter, and the check that keeps "local" honest.

No request in this file leaves the machine: every response is a recorded shape
replayed through an injected transport, which is how the existing adapters are
tested and why the suite runs with no credentials.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.errors import GuideError
from app.providers.base import ContextRequest, ObserveContext, PlanContext
from app.providers.compatible import DeepSeek, Groq, LMStudio, Ollama, OpenRouter
from app.providers.registry import COMPATIBLE

SERVICES = (OpenRouter, Groq, DeepSeek, Ollama, LMStudio)


def transport(payload: dict, status: int = 200, capture: list | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handle)


def answer(body: dict) -> dict:
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(body)}}]}


OBSERVATION = {
    "step_complete": True, "confidence": 0.93, "app_visible": "terminal",
    "ui_changed": True, "anomaly": "none", "note": "A prompt is visible.",
}

CONTEXT = {
    "application": "Windows Terminal", "application_matches_expected": True,
    "screen": "a shell prompt", "stage": "in_progress",
    "controls": [{"label": "Run", "box": [0.1, 0.2, 0.3, 0.4], "kind": "button"}],
    "dialog": "", "error_text": "", "satisfied_later_index": None,
    "confidence": 0.9, "note": "A prompt is visible.",
}


def ctx() -> ObserveContext:
    return ObserveContext(
        success_criterion="A prompt is visible.", expected_result="A prompt.",
        application_key="terminal",
    )


def context_request() -> ContextRequest:
    return ContextRequest(
        success_criterion="A prompt is visible.", expected_result="A prompt.",
        application_key="terminal", step_title="Open the terminal",
    )


# --- every service answers the same way -----------------------------------


@pytest.mark.parametrize("service", SERVICES)
async def test_each_service_serves_the_observe_role(service):
    adapter = service(api_key=SecretStr("k"), transport=transport(answer(OBSERVATION)))
    result = await adapter.observe(ctx(), b"pixels")
    assert result.step_complete is True
    assert result.confidence == 0.93


@pytest.mark.parametrize("service", SERVICES)
async def test_each_service_serves_the_context_role(service):
    adapter = service(api_key=SecretStr("k"), transport=transport(answer(CONTEXT)))
    result = await adapter.observe_context(context_request(), b"pixels")
    assert result.stage == "in_progress"
    assert result.controls[0].label == "Run"


@pytest.mark.parametrize("service", SERVICES)
async def test_the_image_is_sent_and_the_schema_is_declared(service):
    seen: list[httpx.Request] = []
    adapter = service(
        api_key=SecretStr("k"), transport=transport(answer(OBSERVATION), capture=seen)
    )
    await adapter.observe(ctx(), b"pixels")
    body = json.loads(seen[0].content)
    assert body["response_format"]["type"] == "json_schema"
    kinds = [part["type"] for part in body["messages"][1]["content"]]
    assert "image_url" in kinds


# --- the local promise ----------------------------------------------------


@pytest.mark.parametrize("service", (Ollama, LMStudio))
async def test_a_local_service_refuses_a_remote_host(service):
    """The one check that cannot be a warning: a user who chose a local provider
    chose that their screen stays on their machine."""
    adapter = service(base_url="https://someone-elses-server.example/v1/")
    with pytest.raises(GuideError) as raised:
        await adapter.observe(ctx(), b"pixels")
    assert raised.value.body["code"] == "validation_failed"


@pytest.mark.parametrize("service", (Ollama, LMStudio))
async def test_a_local_service_sends_no_credential(service):
    seen: list[httpx.Request] = []
    adapter = service(transport=transport(answer(OBSERVATION), capture=seen))
    await adapter.observe(ctx(), b"pixels")
    assert "authorization" not in {key.lower() for key in seen[0].headers}


@pytest.mark.parametrize("service", (OpenRouter, Groq, DeepSeek))
async def test_a_remote_service_refuses_plain_http(service):
    adapter = service(api_key=SecretStr("k"), base_url="http://api.example.com/v1/")
    with pytest.raises(GuideError) as raised:
        await adapter.plan(PlanContext(goal="Do a thing.", category="setup", application_key="x"))
    assert raised.value.body["code"] == "validation_failed"


# --- failures are reported as themselves ----------------------------------


async def test_a_refusal_is_a_stated_error_not_a_verdict():
    payload = {"choices": [{"finish_reason": "stop", "message": {"refusal": "no"}}]}
    adapter = Groq(api_key=SecretStr("k"), transport=transport(payload))
    with pytest.raises(GuideError) as raised:
        await adapter.observe(ctx(), b"pixels")
    assert raised.value.body["code"] == "answer_declined"


async def test_a_truncated_answer_is_not_treated_as_an_answer():
    payload = {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}
    adapter = Groq(api_key=SecretStr("k"), transport=transport(payload))
    with pytest.raises(GuideError) as raised:
        await adapter.observe(ctx(), b"pixels")
    assert raised.value.body["code"] == "incomplete_answer"


async def test_nonsense_is_refused_rather_than_guessed_at():
    adapter = DeepSeek(api_key=SecretStr("k"), transport=transport(answer({"nope": 1})))
    with pytest.raises(GuideError) as raised:
        await adapter.observe(ctx(), b"pixels")
    assert raised.value.body["code"] == "invalid_answer"


async def test_an_http_failure_names_no_internals():
    adapter = OpenRouter(api_key=SecretStr("k"), transport=transport({}, status=500))
    with pytest.raises(GuideError) as raised:
        await adapter.observe(ctx(), b"pixels")
    assert "k" not in raised.value.body["message"]


# --- the registry ---------------------------------------------------------


def test_every_service_is_registered_with_its_own_models():
    for identifier, (descriptor, adapter) in COMPATIBLE.items():
        assert descriptor.id == identifier
        assert descriptor.models == adapter.models
        assert descriptor.default_model in descriptor.models
        # Every one of them serves the engine roles, which is what makes the
        # choice a real choice rather than a label.
        assert descriptor.supports("observe_context")
        assert descriptor.supports("plan")


def test_local_services_are_marked_local():
    assert COMPATIBLE["ollama"][0].local is True
    assert COMPATIBLE["lmstudio"][0].local is True
    assert COMPATIBLE["groq"][0].local is False
