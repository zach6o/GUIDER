from app.providers.fixture import FixtureProvider
from scripts.smoke_provider import run_analyze, run_context, timed


async def test_new_smoke_roles_accept_the_real_role_contracts():
    assert "observations" in await run_analyze(FixtureProvider())
    assert "stage=" in await run_context(FixtureProvider())


async def test_unexpected_smoke_errors_never_print_payloads_or_credentials():
    async def fails():
        raise RuntimeError("synthetic-secret-must-not-be-printed")

    result = await timed("plan", fails)
    assert not result.ok
    assert result.detail == "RuntimeError"
