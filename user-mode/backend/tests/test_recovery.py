"""Coming back from paused and blocked, and asking for a step again.

Before this, a guide could be stopped four ways — pause, the guard, a failed
instruction, and the user saying the guidance was wrong — and resumed none. These
tests hold the two routes that fix that to doc 05's rules: the context is
reviewed first, no screen permission survives, and a retry rewords a step without
changing anything about it.
"""

from uuid import uuid4

from sqlalchemy import select

from app import models as m
from app.guide.recovery import MAX_ATTEMPTS
from app.worker import tick
from tests.test_feedback import send as feedback
from tests.test_flow import PREFIX
from tests.test_instructions import act, session_state, started
from tests.test_observation import observe, verdict, watching


async def resume(harness, session, **body):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/resume",
        json={"checkpoint_reviewed": True, "mode": "screenshot_only", **body},
        headers={"Idempotency-Key": str(uuid4())},
    )


async def retry(harness, session, step_id, reason="I cannot find it.", key=None):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{step_id}/retries",
        json={"expected_version": session["state_version"], "reason": reason},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


async def blocked_session(harness):
    """A session the user stopped by saying the guidance was wrong."""
    _, session, current = await started(harness)
    response = await feedback(
        harness, session, "incorrect_guidance", current["step"]["id"], "That is not there."
    )
    assert response.status_code == 201, response.text
    return await session_state(harness, session["id"]), current["step"]["id"]


# --- resuming --------------------------------------------------------------


async def test_a_blocked_task_can_be_picked_back_up(harness):
    session, step_id = await blocked_session(harness)
    response = await resume(harness, session)
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["session"]["state"] in {"processing", "awaiting_user_action"}
    # The instruction was withdrawn when the session blocked, so a fresh one is
    # asked for rather than resuming into silence.
    assert body["next_operation_id"] is not None

    await tick(harness.app)
    current = await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    assert current.status_code == 200, current.text
    # The same step, because the user said its guidance was wrong, not that it
    # was done.
    assert current.json()["data"]["step"]["id"] == step_id


async def test_it_will_not_resume_until_the_user_has_looked(harness):
    session, _ = await blocked_session(harness)
    response = await resume(harness, session, checkpoint_reviewed=False)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "context_review_required"
    assert (await session_state(harness, session["id"]))["state"] == "blocked"


async def test_a_paused_task_resumes_to_its_checkpoint(harness):
    _, session, _ = await started(harness)
    paused = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/pause",
        json={"reason": "user"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert paused.status_code == 200, paused.text
    session = await session_state(harness, session["id"])

    response = await resume(harness, session)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["session"]["state"] == "awaiting_user_action"
    # Pausing did not withdraw the instruction, so there is nothing to re-ask for.
    assert response.json()["data"]["next_operation_id"] is None


async def test_watching_is_never_restored_by_resuming(harness):
    """A grant belongs to the run that was interrupted. Doc 05: no grant restored."""
    session, current = await watching(harness, verdict(confidence=0.4))
    await observe(harness, session)
    session = await session_state(harness, session["id"])
    await feedback(harness, session, "incorrect_guidance", current["step"]["id"], "Wrong.")
    session = await session_state(harness, session["id"])

    assert (await resume(harness, session)).status_code == 200
    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
        assert row.observation_active is False
        assert row.observation_mode == "screenshot_only"


async def test_choosing_to_be_watched_again_waits_for_a_fresh_decision(harness):
    session, _ = await blocked_session(harness)
    response = await resume(harness, session, mode="window")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["session"]["state"] == "awaiting_screen_permission"
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.GuideSession, session["id"])).observation_active is False


async def test_a_running_task_has_nothing_to_resume(harness):
    _, session, _ = await started(harness)
    response = await resume(harness, session)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_a_finished_task_cannot_be_resumed(harness):
    _, session, _ = await started(harness)
    stopped = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/stop",
        json={"reason": "user"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert stopped.status_code == 200, stopped.text
    response = await resume(harness, await session_state(harness, session["id"]))
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "session_ended"


async def test_resuming_clears_a_stuck_notice_from_the_interrupted_run(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    # Two claims on one step is the repeated-attempts signal.
    await act(harness, session, step_id, "claim", statement="Done.")
    session = await session_state(harness, session["id"])
    await act(harness, session, step_id, "claim", statement="Done again.")
    session = await session_state(harness, session["id"])
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.GuideSession, session["id"])).stuck_since is not None

    await feedback(harness, session, "incorrect_guidance", step_id, "Wrong step entirely.")
    session = await session_state(harness, session["id"])
    assert (await resume(harness, session)).status_code == 200
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.GuideSession, session["id"])).stuck_since is None


# --- retrying a step -------------------------------------------------------


async def test_a_retry_asks_for_the_step_again_and_changes_nothing_about_it(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    first = current["instruction"]["what"]

    response = await retry(harness, session, step_id)
    assert response.status_code == 202, response.text
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, step_id)
        # Counted, but not advanced, claimed, skipped or verified.
        assert step.attempt_count == 1
        assert step.status in {"instruction_ready", "awaiting_user_action"}
        assert step.verified_at is None
        versions = list(
            await db.scalars(
                select(m.Instruction.version).where(m.Instruction.step_id == step_id)
            )
        )
    assert sorted(versions) == [1, 2]
    again = await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    assert again.json()["data"]["step"]["id"] == step_id
    assert again.json()["data"]["instruction"]["what"] == first  # a fixture says the same thing


async def test_rewording_the_same_step_is_a_guide_going_nowhere(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    for _ in range(2):
        assert (await retry(harness, session, step_id)).status_code == 202
        await tick(harness.app)
        session = await session_state(harness, session["id"])
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.GuideSession, session["id"])).stuck_since is not None


async def test_a_step_cannot_be_reworded_forever(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    for _ in range(MAX_ATTEMPTS):
        assert (await retry(harness, session, step_id)).status_code == 202
        await tick(harness.app)
        session = await session_state(harness, session["id"])
    response = await retry(harness, session, step_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "retry_limit"
    assert "different plan" in response.json()["error"]["message"]


async def test_a_blocked_step_is_refused_however_often_it_is_asked_for(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    async with harness.app.state.sessions() as db, db.begin():
        step = await db.get(m.TaskStep, step_id)
        step.policy_disposition = "block"
    response = await retry(harness, session, step_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "blocked_task"


async def test_only_the_step_you_are_on_can_be_retried(harness):
    _, session, current = await started(harness)
    async with harness.app.state.sessions() as db:
        other = await db.scalar(select(m.TaskStep).where(m.TaskStep.ordinal == 2))
    assert other is not None
    assert other.id != current["step"]["id"]
    response = await retry(harness, session, other.id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_a_replayed_retry_asks_once(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    key = uuid4()
    first = await retry(harness, session, step_id, key=key)
    second = await retry(harness, session, step_id, key=key)
    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["operation_id"] == second.json()["data"]["operation_id"]
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.TaskStep, step_id)).attempt_count == 1
