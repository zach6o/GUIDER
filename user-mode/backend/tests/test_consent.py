from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.guide.observation import MAX_OBSERVATION_CALLS, NOTICE_VERSION
from tests.conftest import on_postgres
from tests.test_flow import PREFIX
from tests.test_instructions import act, session_state, started
from tests.test_observation import StubObserver, frame, observe, verdict


async def consent(harness, session, version=NOTICE_VERSION, key=None):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observation",
        json={
            "expected_version": session["state_version"],
            "consent_version": version,
            "accepted": True,
        },
        headers={"Idempotency-Key": key or str(uuid4())},
    )


async def stop(harness, session):
    return await harness.client.delete(PREFIX + f"/sessions/{session['id']}/observation")


async def watching(harness, *results):
    _, session, current = await started(harness)
    harness.app.state.observer = StubObserver(*(results or (verdict(),)))
    await consent(harness, session)
    return await session_state(harness, session["id"]), current


# --- switching it on ------------------------------------------------------


async def test_watching_is_off_until_it_is_explicitly_switched_on(harness):
    _, session, _ = await started(harness)
    assert session["observation_active"] is False
    assert session["observation_mode"] == "screenshot_only"

    body = (await consent(harness, session)).json()["data"]
    assert body["active"] is True
    assert body["session"]["observation_mode"] == "window"
    assert body["observation_calls_remaining"] == MAX_OBSERVATION_CALLS
    assert body["consent_version"] == NOTICE_VERSION


async def test_the_agreed_notice_version_is_recorded_against_the_user(harness):
    _, session, _ = await started(harness)
    await consent(harness, session)
    async with harness.app.state.sessions() as db:
        user = await db.scalar(
            select(m.User).where(m.User.privacy_notice_version == NOTICE_VERSION)
        )
    assert user is not None


async def test_an_old_notice_must_be_read_again(harness):
    _, session, _ = await started(harness)
    response = await consent(harness, session, version="observation-draft-0")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_version_mismatch"
    # The refusal names the notice the client must show, so it can present the
    # current wording rather than guess what changed.
    assert response.json()["error"]["details"]["current_version"] == NOTICE_VERSION

    current = await session_state(harness, session["id"])
    assert current["observation_active"] is False


async def test_consent_cannot_be_implied(harness):
    _, session, _ = await started(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observation",
        json={"expected_version": session["state_version"], "consent_version": NOTICE_VERSION,
              "accepted": False},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


async def test_switching_on_is_recorded_as_an_event(harness):
    _, session, _ = await started(harness)
    await consent(harness, session)
    async with harness.app.state.sessions() as db:
        event = await db.scalar(
            select(m.GuidanceEvent).where(m.GuidanceEvent.type == "observation.enabled")
        )
    assert event.payload["consent_version"] == NOTICE_VERSION
    assert event.payload["budget"] == MAX_OBSERVATION_CALLS


# --- the counter ----------------------------------------------------------


async def test_the_counter_matches_what_the_server_has_seen(harness):
    """The exit gate, half one: what the overlay shows is the server's own count,
    not a number the browser keeps for itself."""
    session, _ = await watching(harness, verdict(confidence=0.1))
    for expected in (1, 2, 3):
        current = await session_state(harness, session["id"])
        body = (await observe(harness, current)).json()["data"]
        assert body["frames_observed"] == expected
        assert body["observation_calls_remaining"] == MAX_OBSERVATION_CALLS - expected
        assert current["frames_observed"] == expected - 1  # the read before this tick

    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
    assert row.frames_observed == 3
    assert row.observation_calls == 3
    assert (await session_state(harness, session["id"]))["frames_observed"] == 3


async def test_a_refused_frame_is_not_counted(harness):
    session, _ = await watching(harness, verdict(confidence=0.1))
    await observe(harness, session, image="not-base64!")
    current = await session_state(harness, session["id"])
    assert current["frames_observed"] == 0


# --- one tap to stop ------------------------------------------------------


async def test_stopping_switches_it_off_and_moves_the_epoch(harness):
    """The exit gate, half two: stop revokes in-flight work."""
    session, _ = await watching(harness)
    before = session["control_epoch"]

    body = (await stop(harness, session)).json()["data"]
    assert body["active"] is False
    assert body["session"]["control_epoch"] == before + 1
    assert body["session"]["observation_mode"] == "screenshot_only"


async def test_stopping_cancels_queued_work(harness):
    session, current = await watching(harness)
    # Skipping queues the next instruction without running it, so there is
    # genuinely something in flight for the stop to revoke.
    await act(harness, session, current["step"]["id"], "skip", reason="not_applicable")
    session = await session_state(harness, session["id"])
    async with harness.app.state.sessions() as db:
        queued = list(
            await db.scalars(
                select(m.OperationRow).where(m.OperationRow.status.in_(["queued", "running"]))
            )
        )
    assert queued, "there should be work in flight to revoke"

    await stop(harness, session)
    async with harness.app.state.sessions() as db:
        statuses = {row.status for row in await db.scalars(select(m.OperationRow))}
    assert "queued" not in statuses


async def test_nothing_is_observed_after_stopping(harness):
    session, _ = await watching(harness)
    await stop(harness, session)
    current = await session_state(harness, session["id"])
    response = await observe(harness, current)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "observation_off"
    assert harness.app.state.observer.calls == 0


@on_postgres
async def test_a_stop_during_a_check_discards_that_frame(harness):
    """A stop that lands while the provider is busy still wins: the frame is
    dropped without spending budget or advancing a step.

    Needs two connections overlapping, so it runs on PostgreSQL only.
    """
    session, current = await watching(harness)

    class SlowObserver(StubObserver):
        async def observe(self, ctx, image):
            # The user taps stop while this call is outstanding.
            async with harness.app.state.sessions() as other, other.begin():
                row = await other.get(m.GuideSession, session["id"])
                row.observation_active = False
                row.control_epoch += 1
            return await super().observe(ctx, image)

    harness.app.state.observer = SlowObserver(verdict())
    response = await observe(harness, session)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "observation_stopped"

    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
        step = await db.get(m.TaskStep, current["step"]["id"])
        assert await db.scalar(select(m.VerificationResult)) is None
    assert row.observation_calls == 0
    assert step.status != "verified"


async def test_stopping_twice_is_not_an_error(harness):
    session, _ = await watching(harness)
    first = await stop(harness, session)
    second = await stop(harness, session)
    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["data"]["active"] is False


async def test_stopping_is_available_without_a_version_or_a_key(harness):
    """A control that stops something must not fail for being pressed at a bad
    moment, so it takes no expected_version and no idempotency key."""
    session, _ = await watching(harness)
    response = await harness.client.delete(PREFIX + f"/sessions/{session['id']}/observation")
    assert response.status_code == 200


async def test_stopping_keeps_the_frame_count_for_the_record(harness):
    session, _ = await watching(harness, verdict(confidence=0.1))
    await observe(harness, session)
    current = await session_state(harness, session["id"])
    body = (await stop(harness, current)).json()["data"]
    assert body["frames_observed"] == 1

    async with harness.app.state.sessions() as db:
        event = await db.scalar(
            select(m.GuidanceEvent).where(m.GuidanceEvent.type == "observation.stopped")
        )
    assert event.payload["frames_observed"] == 1


async def test_another_owner_cannot_switch_watching_on_or_off(harness):
    session, _ = await watching(harness)
    intruder = {"Authorization": f"Bearer {harness.token(owner=str(uuid4()))}"}
    assert (
        await harness.client.delete(
            PREFIX + f"/sessions/{session['id']}/observation", headers=intruder
        )
    ).status_code in {401, 404}
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observation",
        json={"expected_version": session["state_version"], "consent_version": NOTICE_VERSION,
              "accepted": True},
        headers={"Idempotency-Key": str(uuid4()), **intruder},
    )
    assert response.status_code in {401, 404}


def test_production_still_refuses_to_start():
    from app.config import Settings

    with pytest.raises(RuntimeError) as error:
        Settings(environment="production").check()
    assert "consent notice" in str(error.value)
    assert "ADR-011" in str(error.value)


async def test_a_frame_is_still_never_stored(harness):
    session, _ = await watching(harness, verdict(confidence=0.1))
    await observe(harness, session, image=frame())
    async with harness.app.state.sessions() as db:
        assert (await db.scalars(select(m.ScreenshotRow))).all() == []
