from pydantic import SecretStr
from sqlalchemy import select

from app import models as m
from app.crypto import Sealed, open_sealed, root_key
from app.errors import GuideError
from app.providers.base import PlanContext
from app.providers.fixture import FixtureProvider
from app.providers.settings import for_owner
from tests.conftest import ALICE, BOB

PREFIX = "/api/v1/guide/providers"


async def save(harness, **overrides):
    return await harness.client.post(
        PREFIX + "/bindings",
        json={
            "role": "plan",
            "provider_id": "anthropic",
            "api_key": "test-private-key",
            "accepted": True,
            **overrides,
        },
    )


async def test_secret_is_encrypted_and_never_returned(harness):
    harness.app.state.settings.credential_root = SecretStr("test-root")
    response = await save(harness)
    assert response.status_code == 200, response.text
    assert "test-private-key" not in response.text
    async with harness.app.state.sessions() as db:
        row = await db.scalar(select(m.ProviderBinding))
        assert "test-private-key" not in str(row.sealed_key)
        assert (
            open_sealed(Sealed(**row.sealed_key), root_key("test-root"), ALICE).get_secret_value()
            == "test-private-key"
        )
    catalog = await harness.client.get(PREFIX)
    assert catalog.json()["data"]["bindings"][0]["has_key"] is True
    assert "ciphertext" not in catalog.text


async def test_no_root_refuses_remote_but_local_needs_no_key(harness):
    assert (await save(harness)).status_code == 503
    response = await save(harness, provider_id="ollama", api_key=None)
    assert response.status_code == 200
    assert response.json()["data"]["has_key"] is False


async def test_connections_are_isolated_and_removal_is_owner_scoped(harness):
    assert (await save(harness, provider_id="ollama", api_key=None)).status_code == 200
    harness.client.headers["Authorization"] = f"Bearer {harness.token(BOB)}"
    assert (await harness.client.get(PREFIX)).json()["data"]["bindings"] == []
    await harness.client.delete(PREFIX + "/bindings/plan")
    harness.client.headers["Authorization"] = f"Bearer {harness.token(ALICE)}"
    assert len((await harness.client.get(PREFIX)).json()["data"]["bindings"]) == 1


async def test_consent_model_and_role_are_validated(harness):
    assert (await save(harness, accepted=False)).status_code == 422
    assert (await save(harness, role="execute")).status_code == 422
    assert (await save(harness, model="unknown-model")).status_code == 422


async def test_saved_role_binding_is_used_and_usage_is_counted(harness, monkeypatch):
    assert (await save(harness, provider_id="ollama", api_key=None)).status_code == 200
    seen = []

    def build(provider_id, role, **kwargs):
        seen.append((provider_id, role))
        return FixtureProvider()

    monkeypatch.setattr("app.providers.settings.build_configured", build)
    async with harness.app.state.sessions() as db, db.begin():
        provider = await for_owner(harness.app, db, ALICE, "plan")
        await provider.plan(
            PlanContext(goal="Open a terminal", category="setup", application_key="powershell")
        )
    assert seen == [("ollama", "plan")]
    usage = (await harness.client.get(PREFIX + "/usage")).json()["data"]
    assert usage["calls"] == usage["succeeded"] == 1


async def test_account_delete_preflight_allows_confirmation(harness):
    response = await harness.client.options(
        "/api/v1/guide/account",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,x-confirm-deletion",
        },
    )
    assert response.status_code == 200


async def test_failed_live_provider_calls_still_consume_daily_budget(harness, monkeypatch):
    from tests.test_observation import observe, watching

    session, _ = await watching(harness)
    await save(harness, role="observe", provider_id="ollama", api_key=None)
    # Changing a binding revokes watching; the test explicitly re-enables it.
    async with harness.app.state.sessions() as db, db.begin():
        row = await db.get(m.GuideSession, session["id"])
        row.observation_active = True

    class Failing:
        async def observe(self, *_args):
            raise GuideError(503, "provider_unavailable", "Synthetic provider outage.")

    monkeypatch.setattr("app.providers.settings.build_configured", lambda *_a, **_k: Failing())
    response = await observe(harness, session)
    assert response.status_code == 503, response.text
    usage = (await harness.client.get(PREFIX + "/usage")).json()["data"]
    assert usage["calls"] == 1
    assert usage["succeeded"] == 0


async def test_settings_disclose_active_managed_provider_without_its_key(harness):
    await harness.client.get(PREFIX)
    config = harness.app.state.settings
    config.credential_root = SecretStr("test-root")
    config.managed_provider_id = "anthropic"
    config.managed_provider_key = SecretStr("synthetic-managed-secret")
    async with harness.app.state.sessions() as db, db.begin():
        (await db.get(m.User, ALICE)).provider_tier = "managed"
    response = await harness.client.get(PREFIX)
    assert response.json()["data"]["managed_provider"] == "anthropic"
    assert "synthetic-managed-secret" not in response.text
