import asyncio
import base64
import json
import sys
from datetime import timedelta
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.errors import GuideError
from app.main import create_app
from app.models import now
from app.personal_app import create_personal_app, validate_hosted
from app.personal_keys import PersonalKeys
from app.personal_store import PersonalBase, PersonalKey
from app.personal_types import PersonalPlan, PersonalTick
from app.provider import python_fixture
from app.providers.anthropic import AnthropicClaude
from app.providers.openai import OpenAIVision
from tests.conftest import ALICE, BOB

PREFIX = "/api/v1/local-guide"
KEY = "sk-personal-synthetic-key-not-real"
PLAN = {
    "goal": "Set up VS Code",
    "assumptions": ["Windows desktop"],
    "steps": [
        {
            "title": "Open the website",
            "action": "Open the official VS Code website.",
            "success_criterion": "The VS Code page is visible.",
        },
        {
            "title": "Install VS Code",
            "action": "Install VS Code using its user installer.",
            "success_criterion": "The VS Code welcome window is visible.",
        },
    ],
}
TICK = {
    "observation": "The official page is visible.",
    "action": "Select the Windows link.",
    "where": "In the center of the page.",
    "step_complete": False,
    "confidence": 0.99,
    "target": {"x": 0.5, "y": 0.4, "label": "Windows"},
    "disposition": "guide",
}


@pytest.fixture
async def personal(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'personal.db'}",
        supabase_url="https://fixture.supabase.co",
        credential_root="x" * 40,
        allowed_origins=["https://guider.example"],
        personal_allowed_users=[ALICE, BOB],
        provider_daily_calls=20,
    )
    app = create_personal_app(settings)
    key = ec.generate_private_key(ec.SECP256R1())
    app.state.verifier.keys.get_signing_key_from_jwt = lambda _: SimpleNamespace(
        key=key.public_key()
    )

    def headers(owner=ALICE, expired=False):
        token = jwt.encode(
            {
                "sub": owner,
                "iss": "https://fixture.supabase.co/auth/v1",
                "aud": "authenticated",
                "role": "authenticated",
                "iat": now(),
                "exp": now() + timedelta(minutes=-5 if expired else 30),
            },
            key,
            algorithm="ES256",
            headers={"kid": "fixture"},
        )
        return {"Origin": "https://guider.example", "Authorization": f"Bearer {token}"}

    async with app.state.engine.begin() as db:
        await db.run_sync(PersonalBase.metadata.create_all)
    calls = []
    tick = dict(TICK)

    async def validate(self, key, model):
        calls.append("validate")

    async def proposal(self, key, model, context, schema, image=None):
        calls.append(context)
        return schema.model_validate(PLAN if schema is PersonalPlan else tick)

    monkeypatch.setattr(OpenAIVision, "validate", validate)
    monkeypatch.setattr(OpenAIVision, "personal", proposal)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example"
    ) as client:
        yield SimpleNamespace(app=app, client=client, headers=headers, calls=calls, tick=tick)
    await app.state.engine.dispose()


async def connect(p, owner=ALICE, saved=False):
    headers = p.headers(owner)
    body = {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "accepted_cloud_terms": True,
        "remember_key": True,
        **({"use_saved_key": True} if saved else {"api_key": KEY}),
    }
    response = await p.client.post(PREFIX + "/connection", headers=headers, json=body)
    assert response.status_code == 200, response.text
    headers["X-Guide-Connection"] = response.json()["connection_token"]
    return headers


async def draft(p, headers):
    result = await p.client.post(
        PREFIX + "/plans",
        headers=headers,
        json={"goal": "Set up VS Code", "pasted_steps": "Open site, install VS Code"},
    )
    assert result.status_code == 200, result.text
    return result.json()


def frame(index=0):
    return {"step_index": index, "image_base64": base64.b64encode(python_fixture()).decode()}


async def test_hosted_keys_are_encrypted_private_and_reusable_after_restart(personal):
    p = personal
    await connect(p)
    async with p.app.state.sessions() as db:
        row = await db.scalar(select(PersonalKey))
        assert KEY not in json.dumps(row.sealed)
    listing = await p.client.get(PREFIX + "/saved-keys", headers=p.headers())
    assert listing.json() == {"available": True, "providers": ["openai"]}
    assert KEY not in listing.text
    assert (await p.client.get(PREFIX + "/saved-keys", headers=p.headers(BOB))).json()[
        "providers"
    ] == []
    p.app.state.cloud_connections.items.clear()  # Simulate loss of all transient grants.
    await connect(p, saved=True)
    store = p.app.state.personal_keys
    with pytest.raises(GuideError):
        await store.read(BOB, "openai")


async def test_key_forget_revokes_only_owners_connections(personal):
    p = personal
    alice, bob = await connect(p), await connect(p, BOB)
    assert (
        await p.client.delete(PREFIX + "/saved-keys/openai", headers=p.headers())
    ).status_code == 204
    assert (
        await p.client.post(PREFIX + "/plans", headers=alice, json={"goal": "Help"})
    ).status_code == 401
    assert (
        await p.client.post(PREFIX + "/plans", headers=bob, json={"goal": "Help"})
    ).status_code == 200


async def test_foreign_expired_and_other_owner_tokens_never_unlock_connections(personal):
    p = personal
    alice = await connect(p)
    for headers, expected in [
        ({}, 403),
        ({"Origin": "https://guider.example"}, 401),
        (p.headers(expired=True), 401),
        ({**p.headers(BOB), "X-Guide-Connection": alice["X-Guide-Connection"]}, 401),
    ]:
        response = await p.client.post(PREFIX + "/plans", headers=headers, json={"goal": "Help"})
        assert response.status_code == expected, response.text


async def test_plan_requires_confirmation_scope_and_step_permission(personal):
    p = personal
    headers = await connect(p)
    plan = await draft(p, headers)
    base = PREFIX + "/plans/" + plan["id"]
    assert not plan["confirmed"] and plan["steps"][1]["permission"] == "confirm"
    permissions = {"accepted_automatic_frames": True, "scope_reviewed": True}
    assert (
        await p.client.post(base + "/watch", headers=headers, json=permissions)
    ).status_code == 409
    assert (
        await p.client.post(base + "/confirm", headers=headers, json={"accepted": True})
    ).status_code == 200
    assert (await p.client.post(base + "/frames", headers=headers, json=frame())).status_code == 409
    assert (
        await p.client.post(base + "/watch", headers=headers, json=permissions)
    ).status_code == 200
    p.tick["step_complete"] = True
    result = await p.client.post(base + "/frames", headers=headers, json=frame())
    assert result.status_code == 200, result.text
    assert result.json()["advanced"] and result.json()["guidance"]["target"] is None
    assert result.json()["plan"]["step_index"] == 1
    assert (
        await p.client.post(base + "/frames", headers=headers, json=frame(1))
    ).status_code == 409
    assert (
        await p.client.post(
            base + "/approve-step", headers=headers, json={"accepted": True, "step_index": 1}
        )
    ).status_code == 200
    next(iter(p.app.state.cloud_connections.items.values())).last_call = 0
    result = await p.client.post(base + "/frames", headers=headers, json=frame(1))
    assert result.json()["plan"]["finished"]
    assert not result.json()["plan"]["watching"]
    assert (
        await p.client.post(base + "/frames", headers=headers, json=frame(1))
    ).status_code == 409


async def test_pause_cancels_pending_frame_and_late_result_cannot_advance(personal, monkeypatch):
    p = personal
    headers = await connect(p)
    plan = await draft(p, headers)
    base = PREFIX + "/plans/" + plan["id"]
    await p.client.post(base + "/confirm", headers=headers, json={"accepted": True})
    await p.client.post(
        base + "/watch",
        headers=headers,
        json={"accepted_automatic_frames": True, "scope_reviewed": True},
    )
    entered = asyncio.Event()

    async def delayed(*args):
        entered.set()
        await asyncio.sleep(30)
        return PersonalTick.model_validate({**TICK, "step_complete": True})

    monkeypatch.setattr(OpenAIVision, "personal", delayed)
    checking = asyncio.create_task(p.client.post(base + "/frames", headers=headers, json=frame()))
    await asyncio.wait_for(entered.wait(), 10)
    assert (await p.client.delete(base + "/watch", headers=headers)).status_code == 200
    assert (await checking).status_code == 409
    state = next(iter(p.app.state.cloud_connections.items.values())).workflow
    assert state.index == 0 and not state.watching


async def test_daily_quota_survives_new_connections(personal):
    p = personal
    p.app.state.personal_keys.daily_calls = 1
    await connect(p)
    response = await p.client.post(
        PREFIX + "/connection",
        headers=p.headers(),
        json={"provider": "openai", "use_saved_key": True, "accepted_cloud_terms": True},
    )
    assert response.status_code == 429
    assert p.calls == ["validate"]


async def test_frame_rate_and_uncertain_or_blocked_results_cannot_advance(personal):
    p = personal
    headers = await connect(p)
    plan = await draft(p, headers)
    base = PREFIX + "/plans/" + plan["id"]
    await p.client.post(base + "/confirm", headers=headers, json={"accepted": True})
    await p.client.post(
        base + "/watch",
        headers=headers,
        json={"accepted_automatic_frames": True, "scope_reviewed": True},
    )
    connection = next(iter(p.app.state.cloud_connections.items.values()))
    p.tick.update(step_complete=True, confidence=0.5)
    for _ in range(6):
        connection.last_call = 0
        result = await p.client.post(base + "/frames", headers=headers, json=frame())
        assert result.status_code == 200, result.text
        assert not result.json()["advanced"]
    connection.last_call = 0
    assert (await p.client.post(base + "/frames", headers=headers, json=frame())).status_code == 429
    connection.observation_times.clear()
    p.tick.update(confidence=0.99, action="Enter your password")
    result = await p.client.post(base + "/frames", headers=headers, json=frame())
    assert not result.json()["advanced"]
    assert result.json()["guidance"]["disposition"] == "blocked"
    assert result.json()["guidance"]["target"] is None
    assert not result.json()["plan"]["watching"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_windows_key_store_is_encrypted_and_survives_new_instance(tmp_path):
    store = PersonalKeys(tmp_path)
    store.save("openai", SecretStr(KEY))
    assert KEY.encode() not in (tmp_path / "openai.dpapi").read_bytes()
    assert PersonalKeys(tmp_path).read("openai").get_secret_value() == KEY
    store.forget("openai")
    assert not store.has("openai")


def test_hosted_configuration_requires_auth_encryption_and_durable_storage():
    with pytest.raises(ValueError):
        validate_hosted(Settings(_env_file=None))
    with pytest.raises(ValueError):
        validate_hosted(
            Settings(
                _env_file=None,
                supabase_url="https://test.supabase.co",
                credential_root="x" * 40,
                personal_allowed_users=[ALICE],
            )
        )
    with pytest.raises(RuntimeError):
        create_app(Settings(environment="production"))  # Legacy production guard stays intact.


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_personal_provider_transport_uses_structured_schema_without_tools(provider):
    seen = []

    async def answer(request):
        seen.append(json.loads(request.content))
        body = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(PLAN)}]}
        if provider == "openai":
            body = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(PLAN)}],
                    }
                ],
            }
        return httpx.Response(200, json=body)

    adapter = (
        OpenAIVision(httpx.MockTransport(answer))
        if provider == "openai"
        else AnthropicClaude(transport=httpx.MockTransport(answer))
    )
    result = await adapter.personal(SecretStr(KEY), "test-model", {"goal": "Help"}, PersonalPlan)
    assert result.goal == PLAN["goal"]
    assert "tools" not in seen[0] and KEY not in json.dumps(seen[0])
