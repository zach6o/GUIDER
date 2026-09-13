"""A self-report moves the guide on. It never verifies anything.

Doc 05 allows `awaiting_user_action -> verifying` on an explicit self-report and
returns with the step still `user_claimed`. These tests hold that line from both
sides: the guide reaches its last step with watching off, and no record anywhere
says a step passed.
"""

from uuid import uuid4

from sqlalchemy import select

from app import models as m
from app.worker import tick
from tests.test_flow import PREFIX
from tests.test_instructions import act, session_state, started


async def claim(harness, session, step_id, statement="Done that."):
    response = await act(harness, session, step_id, "claim", statement=statement)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def self_report(harness, session, step_id, claim_id, said="I did that.", **body):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{step_id}/verifications",
        json={
            "expected_version": session["state_version"],
            "claim_id": claim_id,
            "self_report": said,
            **body,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )


async def advance(harness, session_id):
    """Claim the current step, report it done, and let the worker catch up."""
    state = await session_state(harness, session_id)
    current = await harness.client.get(PREFIX + f"/sessions/{session_id}/instruction")
    if current.status_code != 200:
        return None
    step = current.json()["data"]["step"]
    claimed = await claim(harness, state, step["id"])
    state = await session_state(harness, session_id)
    response = await self_report(harness, state, step["id"], claimed["claim_id"])
    assert response.status_code == 200, response.text
    await tick(harness.app)
    return step


# --- what a self-report is worth -----------------------------------------


async def test_a_self_report_records_user_reported_and_never_a_pass(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])

    response = await self_report(
        harness, session, current["step"]["id"], claimed["claim_id"], said="The prompt appeared."
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]

    assert body["verified"] is False
    assert body["verification"]["status"] == "user_reported"
    assert body["verification"]["verifier_kind"] == "self_report"
    assert body["verification"]["evidence_available"] is False
    assert body["verification"]["observed_confidence"] is None
    assert body["verification"]["claim_id"] == claimed["claim_id"]
    # The step keeps the user's word as its status. It is not verified.
    assert body["step"]["status"] == "user_claimed"
    assert body["step"]["verified_at"] is None

    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, current["step"]["id"])
        verification = await db.scalar(select(m.VerificationResult))
    assert step.status == "user_claimed"
    assert step.verified_at is None
    assert verification.reason == "The prompt appeared."
    assert verification.instruction_version == current["instruction"]["version"]


async def test_the_event_for_a_self_report_says_it_did_not_pass(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    await self_report(harness, session, current["step"]["id"], claimed["claim_id"])

    async with harness.app.state.sessions() as db:
        event = await db.scalar(
            select(m.GuidanceEvent).where(m.GuidanceEvent.type == "verification.completed")
        )
    assert event.payload["passed"] is False
    assert event.payload["status"] == "user_reported"


# --- what it buys ---------------------------------------------------------


async def test_a_self_report_prepares_the_next_step(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    response = await self_report(harness, session, current["step"]["id"], claimed["claim_id"])
    assert response.json()["data"]["next_operation_id"]
    await tick(harness.app)

    following = (
        await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    ).json()["data"]
    assert following["step"]["ordinal"] == 2
    assert following["instruction"]["id"] != current["instruction"]["id"]
    assert following["session"]["state"] == "awaiting_user_action"


async def test_a_self_reported_step_is_not_handed_out_again(harness):
    _, session, current = await started(harness)
    first = await advance(harness, session["id"])
    second = await advance(harness, session["id"])
    assert first["ordinal"] == 1
    assert second["ordinal"] == 2

    async with harness.app.state.sessions() as db:
        statuses = {
            row.ordinal: row.status
            for row in await db.scalars(select(m.TaskStep).order_by(m.TaskStep.ordinal))
        }
    assert statuses[1] == "user_claimed"


async def test_a_whole_plan_can_be_self_reported_without_claiming_success(harness):
    _, session, _ = await started(harness)
    ordinals = []
    for _ in range(4):
        step = await advance(harness, session["id"])
        if step is None:
            break
        ordinals.append(step["ordinal"])

    assert ordinals == [1, 2, 3]
    final = await session_state(harness, session["id"])
    # Every step was reported done by the user, and the task is still not achieved.
    assert final["state"] == "awaiting_user_action"
    assert final["outcome"] is None
    assert final["current_step_id"] is None

    async with harness.app.state.sessions() as db:
        verifications = list(await db.scalars(select(m.VerificationResult)))
        steps = list(await db.scalars(select(m.TaskStep)))
        kinds = list(await db.scalars(select(m.GuidanceEvent.type)))
    assert {verification.status for verification in verifications} == {"user_reported"}
    assert not [step for step in steps if step.status == "verified"]
    assert not [step for step in steps if step.verified_at]
    assert "plan.steps_exhausted" in kinds


# --- refusals -------------------------------------------------------------


async def test_evidence_is_refused_rather_than_quietly_downgraded(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    response = await self_report(
        harness,
        session,
        current["step"]["id"],
        claimed["claim_id"],
        evidence_ids=[str(uuid4())],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "evidence_required"

    async with harness.app.state.sessions() as db:
        assert await db.scalar(select(m.VerificationResult)) is None


async def test_an_empty_self_report_is_refused(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    response = await self_report(
        harness, session, current["step"]["id"], claimed["claim_id"], said="   "
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "evidence_required"


async def test_a_self_report_needs_a_claim_of_its_own_step(harness):
    _, session, current = await started(harness)
    response = await self_report(
        harness, session, current["step"]["id"], str(uuid4())
    )
    assert response.status_code == 404


async def test_a_superseded_claim_cannot_be_reported_on(harness):
    _, session, current = await started(harness)
    first = await claim(harness, session, current["step"]["id"], statement="First.")
    session = await session_state(harness, session["id"])
    await claim(harness, session, current["step"]["id"], statement="Actually now.")
    session = await session_state(harness, session["id"])

    response = await self_report(harness, session, current["step"]["id"], first["claim_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_a_stale_version_is_refused(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    # The claim moved the version on; this body still carries the older one.
    response = await self_report(harness, session, current["step"]["id"], claimed["claim_id"])
    assert response.status_code == 409


async def test_reporting_is_idempotent_on_a_retried_key(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    key = {"Idempotency-Key": str(uuid4())}
    body = {
        "expected_version": session["state_version"],
        "claim_id": claimed["claim_id"],
        "self_report": "I did that.",
    }
    path = PREFIX + f"/sessions/{session['id']}/steps/{current['step']['id']}/verifications"
    first = await harness.client.post(path, json=body, headers=key)
    second = await harness.client.post(path, json=body, headers=key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]

    async with harness.app.state.sessions() as db:
        assert len(list(await db.scalars(select(m.VerificationResult)))) == 1


async def test_the_route_is_owner_scoped(harness):
    _, session, current = await started(harness)
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{current['step']['id']}/verifications",
        json={
            "expected_version": session["state_version"],
            "claim_id": claimed["claim_id"],
            "self_report": "I did that.",
        },
        headers={
            "Idempotency-Key": str(uuid4()),
            "Authorization": f"Bearer {harness.token(owner=str(uuid4()))}",
        },
    )
    assert response.status_code in {401, 404}
