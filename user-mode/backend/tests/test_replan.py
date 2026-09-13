"""Being stuck, and asking for a different plan.

Two rules run through all of this. Noticing that a guide is going nowhere never
changes session state — it is said once, and the user decides what to do about
it. And a replacement plan may only propose what is left: every settled step is
carried across exactly as it was, verified steps included.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.guide.replan import STUCK_AFTER
from app.providers.fixture import FIXTURE_REPLAN
from app.worker import tick
from tests.test_flow import PREFIX
from tests.test_instructions import session_state, started
from tests.test_observation import StubObserver, frame, verdict
from tests.test_self_report import advance, claim, self_report


async def ask_replan(harness, session, reason="user", **overrides):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/replan",
        json={"expected_version": session["state_version"], "reason": reason, **overrides},
        headers={"Idempotency-Key": str(uuid4())},
    )


async def plan_of(harness, plan_id):
    response = await harness.client.get(PREFIX + f"/plans/{plan_id}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def replanned(harness, reason="user"):
    """A started session, one step reported done, then a replacement plan."""
    _, session, _ = await started(harness)
    first = await advance(harness, session["id"])
    session = await session_state(harness, session["id"])
    response = await ask_replan(harness, session, reason)
    assert response.status_code == 202, response.text
    await tick(harness.app)
    return first, await session_state(harness, session["id"]), response.json()["data"]


async def observe_with(harness, session, observer, image=None):
    harness.app.state.observer = observer
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observe",
        json={
            "expected_version": session["state_version"],
            "image_base64": image or frame(),
            "admitted_at": m.now().isoformat(),
        },
    )


async def watching(harness, session):
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observation",
        json={
            "expected_version": session["state_version"],
            "consent_version": "observation-draft-1",
            "accepted": True,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return await session_state(harness, session["id"])


async def events_of(harness, session_id):
    async with harness.app.state.sessions() as db:
        return list(
            await db.scalars(
                select(m.GuidanceEvent)
                .where(m.GuidanceEvent.session_id == session_id)
                .order_by(m.GuidanceEvent.sequence)
            )
        )


# --- noticing ------------------------------------------------------------


async def test_a_screen_that_stopped_matching_is_reported_once(harness):
    _, session, _ = await started(harness)
    session = await watching(harness, session)
    observer = StubObserver(
        verdict(step_complete=False, confidence=0.1, anomaly="different_app"),
        verdict(step_complete=False, confidence=0.1, anomaly="different_app"),
    )
    assert (await observe_with(harness, session, observer)).status_code == 200
    session = await session_state(harness, session["id"])
    assert (await observe_with(harness, session, observer)).status_code == 200

    stuck = [event for event in await events_of(harness, session["id"])
             if event.type == "session.stuck_detected"]
    assert len(stuck) == 1
    assert stuck[0].payload["reason"] == "anomaly:different_app"

    current = await session_state(harness, session["id"])
    # Said, not acted on: the session is exactly where it was.
    assert current["state"] == "awaiting_user_action"
    assert current["outcome"] is None


async def test_being_stuck_does_not_advance_or_block_anything(harness):
    _, session, current = await started(harness)
    session = await watching(harness, session)
    observer = StubObserver(verdict(step_complete=False, confidence=0.2, anomaly="outdated_ui"))
    await observe_with(harness, session, observer)

    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, current["step"]["id"])
        row = await db.get(m.GuideSession, session["id"])
    assert step.status == "awaiting_user_action"
    assert step.verified_at is None
    assert row.stuck_since is not None


async def test_saying_done_twice_on_one_step_counts_as_stuck(harness):
    _, session, current = await started(harness)
    await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    await claim(harness, session, current["step"]["id"])

    stuck = [event for event in await events_of(harness, session["id"])
             if event.type == "session.stuck_detected"]
    assert [event.payload["reason"] for event in stuck] == ["repeated_attempts"]


async def test_a_step_nobody_finishes_is_noticed_after_a_while(harness):
    _, session, current = await started(harness)
    async with harness.app.state.sessions() as db, db.begin():
        instruction = await db.get(m.Instruction, current["instruction"]["id"])
        instruction.created_at = m.now() - STUCK_AFTER - timedelta(minutes=1)

    await claim(harness, session, current["step"]["id"])
    stuck = [event for event in await events_of(harness, session["id"])
             if event.type == "session.stuck_detected"]
    assert [event.payload["reason"] for event in stuck] == ["no_progress"]


# --- replanning ----------------------------------------------------------


async def test_a_replacement_plan_keeps_what_is_already_done(harness):
    first, session, pending = await replanned(harness)
    async with harness.app.state.sessions() as db:
        operation = await db.get(m.OperationRow, pending["operation_id"])
    plan = await plan_of(harness, operation.result_ref)

    assert plan["version"] == 2
    assert plan["status"] == "draft"
    # The step already reported done is carried across, in place, untouched.
    carried = plan["steps"][0]
    assert carried["title"] == first["title"]
    assert carried["status"] == "user_claimed"
    assert [step["title"] for step in plan["steps"][1:]] == [
        step["title"] for step in FIXTURE_REPLAN
    ]
    assert session["state"] == "awaiting_user_confirmation"


async def test_a_verified_step_survives_a_replan_untouched(harness):
    _, session, current = await started(harness)
    session = await watching(harness, session)
    observer = StubObserver(verdict(step_complete=True, confidence=0.97))
    assert (await observe_with(harness, session, observer)).status_code == 200
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        verified = await db.get(m.TaskStep, current["step"]["id"])
        verified_at = verified.verified_at
    assert verified.status == "verified"

    session = await session_state(harness, session["id"])
    assert (await ask_replan(harness, session, "anomaly")).status_code == 202
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        original = await db.get(m.TaskStep, current["step"]["id"])
        copy = await db.scalar(
            select(m.TaskStep).where(m.TaskStep.previous_step_id == current["step"]["id"])
        )
    # The original is exactly as it was, and the copy carries its evidence.
    assert original.status == "verified"
    assert original.verified_at == verified_at
    assert copy is not None
    assert copy.status == "verified"
    assert copy.verified_at == verified_at
    assert copy.ordinal == 1


async def test_the_replacement_is_a_draft_the_user_still_has_to_confirm(harness):
    _, session, pending = await replanned(harness)
    async with harness.app.state.sessions() as db:
        operation = await db.get(m.OperationRow, pending["operation_id"])
        row = await db.get(m.GuideSession, session["id"])
    # Confirmed version still points at the plan being followed until confirmed.
    assert row.confirmed_plan_version == 1
    assert (await plan_of(harness, operation.result_ref))["status"] == "draft"
    assert session["current_step_id"] is None


async def test_the_guide_continues_on_the_new_plan_after_confirmation(harness):
    first, session, pending = await replanned(harness)
    async with harness.app.state.sessions() as db:
        operation = await db.get(m.OperationRow, pending["operation_id"])
    plan = await plan_of(harness, operation.result_ref)

    confirmed = await harness.client.post(
        PREFIX + f"/plans/{plan['id']}/confirm",
        json={"expected_version": session["state_version"], "plan_version": plan["version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert confirmed.status_code == 200, confirmed.text
    session = confirmed.json()["data"]["session"]

    started_again = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/start",
        json={"expected_version": session["state_version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert started_again.status_code == 202, started_again.text
    await tick(harness.app)

    current = (
        await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    ).json()["data"]
    # The carried step is behind the guide; the first new step is what is asked.
    assert current["step"]["title"] == FIXTURE_REPLAN[0]["title"]
    assert current["step"]["title"] != first["title"]


async def test_replanning_clears_the_stuck_marker(harness):
    _, session, current = await started(harness)
    await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])

    assert (await ask_replan(harness, session, "stuck")).status_code == 202
    await tick(harness.app)
    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
    assert row.stuck_since is None


async def test_the_planner_is_told_why_without_being_told_what_is_on_screen(harness):
    _, session, current = await started(harness)
    session = await watching(harness, session)
    await observe_with(
        harness, session,
        StubObserver(verdict(step_complete=False, confidence=0.1, anomaly="different_os")),
    )
    session = await session_state(harness, session["id"])

    seen: list = []
    original = harness.app.state.providers.select

    def capture(role, **kwargs):
        provider = original(role, **kwargs)
        if role != "plan":
            return provider
        planned = provider.plan

        async def record(ctx):
            seen.append(ctx)
            return await planned(ctx)

        provider.plan = record
        return provider

    harness.app.state.providers.select = capture
    try:
        assert (await ask_replan(harness, session, "anomaly")).status_code == 202
        await tick(harness.app)
    finally:
        harness.app.state.providers.select = original

    assert len(seen) == 1
    context = seen[0]
    assert context.reason == "anomaly"
    assert context.anomaly == "different_os"
    # Only the planner's own earlier words, never anything read from a screen.
    assert context.completed == []
    assert set(context.model_dump()) == {
        "goal", "category", "application_key", "reason", "completed", "anomaly",
    }


# --- refusals ------------------------------------------------------------


async def test_replanning_needs_a_step_to_be_waiting(harness):
    _, session, plan_pending = await replanned(harness)
    # The session is awaiting confirmation of the replacement: not a moment to
    # ask for another one.
    response = await ask_replan(harness, session)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert plan_pending["operation_id"]


async def test_a_stale_version_cannot_replan(harness):
    _, session, current = await started(harness)
    await claim(harness, session, current["step"]["id"])
    response = await ask_replan(harness, session)  # version is now behind
    assert response.status_code == 409


async def test_replanning_is_idempotent_on_a_retried_key(harness):
    _, session, _ = await started(harness)
    key = {"Idempotency-Key": str(uuid4())}
    body = {"expected_version": session["state_version"], "reason": "user"}
    path = PREFIX + f"/sessions/{session['id']}/replan"
    first = await harness.client.post(path, json=body, headers=key)
    second = await harness.client.post(path, json=body, headers=key)
    assert first.status_code == second.status_code == 202
    assert first.json()["data"] == second.json()["data"]

    async with harness.app.state.sessions() as db:
        operations = list(await db.scalars(
            select(m.OperationRow).where(m.OperationRow.kind == "replan")
        ))
    assert len(operations) == 1


async def test_the_replan_route_is_owner_scoped(harness):
    _, session, _ = await started(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/replan",
        json={"expected_version": session["state_version"], "reason": "user"},
        headers={
            "Idempotency-Key": str(uuid4()),
            "Authorization": f"Bearer {harness.token(owner=str(uuid4()))}",
        },
    )
    assert response.status_code in {401, 404}


async def test_a_failed_replan_leaves_the_guide_where_it_was(harness):
    _, session, current = await started(harness)
    assert (await ask_replan(harness, session)).status_code == 202

    async with harness.app.state.sessions() as db, db.begin():
        operation = await db.scalar(
            select(m.OperationRow).where(m.OperationRow.kind == "replan")
        )
        operation.deadline_at = m.now() - timedelta(seconds=1)
    await tick(harness.app)

    final = await session_state(harness, session["id"])
    # Recovery goes through blocked, like a failed instruction, and the step the
    # user was on is still the checkpoint.
    assert final["state"] == "blocked"
    assert final["checkpoint_state"] == "awaiting_user_action"
    async with harness.app.state.sessions() as db:
        plans = list(await db.scalars(select(m.TaskPlan)))
        step = await db.get(m.TaskStep, current["step"]["id"])
    assert len(plans) == 1  # nothing half-written
    assert step.status in {"awaiting_user_action", "instruction_ready"}


@pytest.mark.parametrize("reason", ["stuck", "anomaly", "user"])
async def test_every_reason_is_accepted_and_recorded(harness, reason):
    _, session, _ = await started(harness)
    assert (await ask_replan(harness, session, reason)).status_code == 202
    requested = [event for event in await events_of(harness, session["id"])
                 if event.type == "session.replan_requested"]
    assert [event.payload["reason"] for event in requested] == [reason]


async def test_a_self_reported_step_is_carried_and_not_asked_again(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    await self_report(harness, session, current["step"]["id"], claimed["claim_id"])
    await tick(harness.app)

    session = await session_state(harness, session["id"])
    assert (await ask_replan(harness, session, "user")).status_code == 202
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        copy = await db.scalar(
            select(m.TaskStep).where(m.TaskStep.previous_step_id == current["step"]["id"])
        )
        carried = await db.scalar(
            select(m.VerificationResult).where(m.VerificationResult.step_id == copy.id)
        )
    assert copy.status == "user_claimed"
    assert carried is not None
    assert carried.status == "user_reported"
    assert carried.evidence_available is False
