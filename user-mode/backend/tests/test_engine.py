"""The 05 transition table, written out independently of the engine.

If the engine and this table disagree, one of them is wrong about the
specification. Read this file against doc 05, not against engine.py.
"""

import pytest

from app.errors import GuideError
from app.guide.engine import ALL_STATES, allowed, transition
from tests.conftest import on_postgres
from tests.test_flow import PREFIX, create

PRIORITY = {"paused", "stopping", "expired", "failed"}

# source -> every target doc 05 permits, excluding the self-transition that every
# nonterminal state allows for same-state commands.
EXPECTED: dict[str, set[str]] = {
    "task_created": {"analyzing", "blocked"} | PRIORITY,
    "analyzing": {"task_created", "awaiting_user_confirmation", "plan_ready", "blocked"} | PRIORITY,
    "plan_ready": {"awaiting_user_confirmation", "blocked"} | PRIORITY,
    "awaiting_user_confirmation": {"analyzing", "awaiting_screen_permission", "active", "blocked"}
    | PRIORITY,
    "awaiting_screen_permission": {"active", "blocked"} | PRIORITY,
    "active": {"capturing", "processing", "awaiting_user_confirmation", "blocked"} | PRIORITY,
    "capturing": {"processing", "awaiting_user_confirmation", "blocked"} | PRIORITY,
    "processing": {
        "instruction_ready",
        "verifying",
        "awaiting_user_action",
        "awaiting_user_confirmation",
        "blocked",
    }
    | PRIORITY,
    "instruction_ready": {"awaiting_user_action", "awaiting_user_confirmation", "blocked"}
    | PRIORITY,
    "awaiting_user_action": {
        "verifying",
        "capturing",
        "processing",
        "completed",
        "awaiting_user_confirmation",
        "blocked",
    }
    | PRIORITY,
    "verifying": {"active", "awaiting_user_action", "completed", "awaiting_user_confirmation",
                  "blocked"} | PRIORITY,
    # Resume targets only. A diagnostic analysis here stays in the same state.
    "paused": {"task_created", "awaiting_user_confirmation", "awaiting_user_action",
               "awaiting_screen_permission", "stopping", "expired", "failed"},
    "blocked": {"task_created", "awaiting_user_confirmation", "awaiting_user_action",
                "awaiting_screen_permission"} | PRIORITY,
    # Cleanup is already under way: no pause, no expiry, no failure detour.
    "stopping": {"completed"},
    "completed": set(),
    "failed": set(),
    "expired": set(),
}


@pytest.mark.parametrize("source", sorted(ALL_STATES))
def test_every_state_moves_exactly_where_doc_05_allows(source):
    permitted = EXPECTED[source]
    if permitted:  # Terminal states allow nothing, not even a same-state edit.
        permitted = permitted | {source}
    actual = {target for target in ALL_STATES if allowed(source, target)}
    assert actual == permitted


@pytest.mark.parametrize("state", sorted(ALL_STATES))
def test_the_table_covers_every_state(state):
    assert state in EXPECTED


@pytest.mark.parametrize("terminal", ["completed", "failed", "expired"])
def test_a_terminal_session_never_moves_again(terminal):
    assert not any(allowed(terminal, target) for target in ALL_STATES)


def test_same_state_commands_are_permitted_while_running():
    assert allowed("awaiting_user_action", "awaiting_user_action")
    assert allowed("paused", "paused")


def test_stopping_is_not_interruptible():
    for target in ("paused", "expired", "failed", "blocked", "analyzing"):
        assert not allowed("stopping", target)


def test_a_plan_cannot_be_skipped():
    assert not allowed("task_created", "awaiting_user_confirmation")
    assert not allowed("task_created", "active")
    assert not allowed("plan_ready", "active")


def test_guidance_cannot_start_without_confirmation_or_permission():
    assert not allowed("awaiting_user_confirmation", "awaiting_user_action")
    assert not allowed("awaiting_screen_permission", "capturing")


# --- the engine is the gatekeeper, not a helper --------------------------


async def test_the_engine_refuses_an_unlisted_move(harness):
    created = await create(harness)
    session_id = created.json()["data"]["session"]["id"]
    async with harness.app.state.sessions() as db, db.begin():
        from app import models as m

        session = await db.get(m.GuideSession, session_id)
        with pytest.raises(GuideError) as error:
            await transition(db, session, "verifying", "test", "request")
    assert error.value.status == 409
    assert error.value.body["code"] == "invalid_transition"


async def test_a_refused_move_leaves_the_session_untouched(harness):
    created = await create(harness)
    session_id = created.json()["data"]["session"]["id"]
    before = (await harness.client.get(PREFIX + f"/sessions/{session_id}")).json()["data"]
    async with harness.app.state.sessions() as db, db.begin():
        from app import models as m

        session = await db.get(m.GuideSession, session_id)
        with pytest.raises(GuideError):
            await transition(db, session, "completed", "test", "request")
    after = (await harness.client.get(PREFIX + f"/sessions/{session_id}")).json()["data"]
    assert (after["state"], after["state_version"]) == (before["state"], before["state_version"])


async def test_a_permitted_move_advances_the_version_and_records_an_event(harness):
    created = await create(harness)
    session_id = created.json()["data"]["session"]["id"]
    async with harness.app.state.sessions() as db, db.begin():
        from app import models as m

        session = await db.get(m.GuideSession, session_id)
        before = session.state_version
        await transition(db, session, "analyzing", "plan_requested", "request")
        assert session.state_version == before + 1

    from sqlalchemy import select

    from app import models as m

    async with harness.app.state.sessions() as db:
        kinds = list(
            await db.scalars(
                select(m.GuidanceEvent.type).where(m.GuidanceEvent.session_id == session_id)
            )
        )
    assert "session.state_changed" in kinds


async def test_nothing_outside_the_engine_writes_session_state():
    """`service.change` is gone: the only writer is app.guide.engine.transition."""
    from app import service

    assert not hasattr(service, "change")
    assert not hasattr(service, "event")


# --- per-owner serialization, which only PostgreSQL actually enforces ----


@on_postgres
async def test_two_confirmations_of_one_plan_do_not_both_win(harness):
    """The owner row lock serializes mutations. The loser sees the version the
    winner advanced and is refused, rather than confirming twice."""
    import asyncio

    from tests.test_planning import confirm, planned

    _, session, plan = await planned(harness)
    first, second = await asyncio.gather(
        confirm(harness, session, plan),
        confirm(harness, session, plan),
        return_exceptions=True,
    )
    codes = sorted(
        response.status_code for response in (first, second) if not isinstance(response, Exception)
    )
    assert codes == [200, 409], codes
