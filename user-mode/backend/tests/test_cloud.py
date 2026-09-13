import asyncio
import base64
import json
import time

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.provider import python_fixture
from app.providers.openai import OpenAIVision
from app.providers.registry import OPENAI

KEY = "sk-test-not-a-real-key-1234567890"
ORIGIN = "http://127.0.0.1:5173"
PREFIX = "/api/v1/local-guide"
ANSWER = {
    "observation": "The terminal shows a missing Python package.",
    "next_step": "Check the interpreter version with python --version.",
    "where": "In the same terminal window.",
    "check_for": "A Python version number.",
    "question": "",
    "disposition": "guide",
}


@pytest.fixture
async def cloud(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            storage_path=tmp_path / "media",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'unused.db'}",
        ),
        start_worker=False,
    )
    calls = []

    async def provider(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"id": "gpt-4.1-mini"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(ANSWER)}],
                    },
                ],
            },
        )

    # The connection stores which provider it belongs to and the registry builds
    # the adapter per call, so a test swaps the registration rather than an
    # instance hanging off app.state.
    answer_with(app, provider)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1:8000",
        headers={"Origin": ORIGIN},
    ) as client:
        yield app, client, calls
    await app.state.engine.dispose()


def answer_with(app, handler):
    """Point the `guide` role at a transport that answers however this test needs."""
    app.state.providers.register(
        OPENAI, lambda: OpenAIVision(httpx.MockTransport(handler))
    )


def answer_with_adapter(app, adapter):
    app.state.providers.register(OPENAI, lambda: adapter)


async def connect(client):
    response = await client.post(
        PREFIX + "/connection",
        json={
            "api_key": KEY,
            "model": "gpt-4.1-mini",
            "accepted_cloud_terms": True,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["connection_token"]}


def frame(**overrides):
    return {
        "goal": "Help me run Python",
        "question": "",
        "previous_step": "",
        "image_base64": base64.b64encode(python_fixture()).decode(),
        "reviewed": True,
        **overrides,
    }


async def test_cloud_request_uses_reviewed_image_no_tools_no_storage(cloud):
    app, client, calls = cloud
    headers = await connect(client)
    response = await client.post(PREFIX + "/checks", json=frame(), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == ANSWER
    payload = json.loads(calls[-1].content)
    assert str(calls[-1].url) == "https://api.openai.com/v1/responses"
    assert calls[-1].headers["authorization"] == "Bearer " + KEY
    assert payload["store"] is False
    assert "tools" not in payload and "previous_response_id" not in payload
    assert payload["text"]["format"]["strict"] is True
    assert payload["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert KEY not in json.dumps(payload) and KEY not in response.text
    assert not app.state.settings.storage_path.exists()


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:9999", ""])
async def test_foreign_origins_cannot_connect(cloud, origin):
    _, client, calls = cloud
    response = await client.post(
        PREFIX + "/connection",
        headers={"Origin": origin},
        json={
            "api_key": KEY,
            "accepted_cloud_terms": True,
        },
    )
    assert response.status_code == 403
    assert calls == []


async def test_rebinding_host_is_rejected(cloud):
    _, client, calls = cloud
    response = await client.post(
        PREFIX + "/connection",
        headers={"Host": "evil.example:8000"},
        json={"api_key": KEY, "accepted_cloud_terms": True},
    )
    assert response.status_code == 403
    assert calls == []


async def test_review_and_capability_are_required(cloud):
    _, client, calls = cloud
    assert (await client.post(PREFIX + "/checks", json=frame())).status_code == 401
    headers = await connect(client)
    assert (
        await client.post(PREFIX + "/checks", json=frame(reviewed=False), headers=headers)
    ).status_code == 422
    assert len(calls) == 1  # Model-access check only; no paid vision call.


async def test_disconnect_clears_key_and_rejects_reuse(cloud):
    app, client, _ = cloud
    headers = await connect(client)
    connection = next(iter(app.state.cloud_connections.items.values()))
    assert (await client.delete(PREFIX + "/connection", headers=headers)).status_code == 204
    assert connection.key.get_secret_value() == ""
    assert not app.state.cloud_connections.items
    assert (await client.post(PREFIX + "/checks", json=frame(), headers=headers)).status_code == 401
    assert (await client.delete(PREFIX + "/connection", headers=headers)).status_code == 204


async def test_expiry_clears_key(cloud):
    app, client, _ = cloud
    headers = await connect(client)
    connection = next(iter(app.state.cloud_connections.items.values()))
    connection.expires = time.monotonic() - 1
    assert (await client.post(PREFIX + "/checks", json=frame(), headers=headers)).status_code == 401
    assert connection.key.get_secret_value() == ""


async def test_cancel_discards_in_flight_result(cloud):
    app, client, _ = cloud
    headers = await connect(client)
    entered = asyncio.Event()

    async def delayed(*_args):
        entered.set()
        await asyncio.sleep(60)

    stalled = OpenAIVision()
    stalled.analyze = delayed
    answer_with_adapter(app, stalled)
    checking = asyncio.create_task(client.post(PREFIX + "/checks", json=frame(), headers=headers))
    await asyncio.wait_for(entered.wait(), 5)
    assert (await client.post(PREFIX + "/checks", json=frame(), headers=headers)).status_code == 409
    assert (await client.post(PREFIX + "/cancel", json={}, headers=headers)).status_code == 204
    response = await checking
    assert response.status_code == 409
    assert "observation" not in response.json()


async def test_provider_error_does_not_echo_secret(cloud):
    app, client, _ = cloud
    answer_with(app, (
            lambda _: httpx.Response(
                401,
                json={"error": {"message": "Incorrect API key: " + KEY}},
            )
        )
    )
    response = await client.post(
        PREFIX + "/connection",
        json={
            "api_key": KEY,
            "accepted_cloud_terms": True,
        },
    )
    assert response.status_code == 401
    assert KEY not in response.text
    assert not app.state.cloud_connections.items


@pytest.mark.parametrize("next_step", [ANSWER["next_step"], "Enter your password."])
async def test_blocked_output_has_no_action(cloud, next_step):
    app, client, _ = cloud
    headers = await connect(client)
    answer_with(app, (
            lambda _: httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {**ANSWER, "disposition": "blocked", "next_step": next_step}
                                    ),
                                },
                            ],
                        }
                    ],
                },
            )
        )
    )
    response = await client.post(PREFIX + "/checks", json=frame(), headers=headers)
    assert response.status_code == 200
    assert response.json()["disposition"] == "blocked"
    assert response.json()["next_step"] == response.json()["where"] == ""


async def test_malformed_image_never_reaches_provider(cloud):
    _, client, calls = cloud
    headers = await connect(client)
    response = await client.post(
        PREFIX + "/checks", json=frame(image_base64="not-base64!"), headers=headers
    )
    assert response.status_code == 422
    assert len(calls) == 1


async def test_local_capability_does_not_unlock_supabase_routes(cloud):
    _, client, _ = cloud
    headers = await connect(client)
    response = await client.get("/api/v1/guide/sessions", headers=headers)
    assert response.status_code in {401, 503}  # Supabase remains required, no local auth bypass.
