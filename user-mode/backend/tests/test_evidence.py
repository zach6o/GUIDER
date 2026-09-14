"""Checking a step against a screenshot, rather than taking the user's word.

The promise being completed here is the product's central one: a step is
`verified` only when something looked at a screen and agreed. These tests hold
both halves of that — that evidence can now earn the badge, and that it only
earns it on the same bands the live path uses.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.guide.evidence import outcome_for
from app.worker import tick
from tests.test_flow import PREFIX, upload
from tests.test_instructions import session_state, started
from tests.test_observation import StubObserver, verdict
from tests.test_self_report import claim


async def share(harness, task, session):
    """Upload one screenshot against this task, as evidence."""
    class Created:
        def json(self):
            return {"data": {"task": task, "session": session}}

    response = await upload(harness, Created())
    assert response.status_code == 201, response.text
    return response.json()["data"]["screenshot"]


async def submit(harness, session, step_id, claim_id, evidence_id):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{step_id}/verifications",
        json={
            "expected_version": session["state_version"],
            "claim_id": claim_id,
            "evidence_ids": [evidence_id],
        },
        headers={"Idempotency-Key": str(uuid4())},
    )


async def checked(harness, *results):
    """A started session with a claim on step one and a screenshot to check."""
    created, session, current = await started(harness)
    harness.app.state.observer = StubObserver(*(results or (verdict(),)))
    task = created.json()["data"]["task"]
    step_id = current["step"]["id"]
    image = await share(harness, task, session)
    # Uploading is a same-state transition, so the version moved: read it back
    # before claiming, exactly as a client would.
    session = await session_state(harness, session["id"])
    claimed = await claim(harness, session, step_id)
    session = await session_state(harness, session["id"])
    return session, step_id, claimed["claim_id"], image["id"]


# --- the bands ------------------------------------------------------------


@pytest.mark.parametrize(
    ("complete", "confidence", "status"),
    [
        (True, 0.99, "passed"), (True, 0.85, "passed"),
        (True, 0.84, "inconclusive"), (True, 0.60, "inconclusive"),
        (True, 0.59, "mismatch"), (False, 0.99, "mismatch"),
    ],
)
def test_evidence_is_held_to_the_same_bands_as_a_live_frame(complete, confidence, status):
    result = verdict(step_complete=complete, confidence=confidence)
    assert outcome_for(result)[0] == status
    assert outcome_for(result)[1] is (status == "passed")


# --- a pass ---------------------------------------------------------------


async def test_a_screenshot_can_finally_verify_a_step(harness):
    session, step_id, claim_id, image_id = await checked(harness, verdict(confidence=0.95))
    response = await submit(harness, session, step_id, claim_id, image_id)
    assert response.status_code == 202, response.text
    assert response.json()["data"]["operation_id"]
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, step_id)
        assert step.status == "verified"
        assert step.verified_at is not None
        results = list(
            await db.scalars(select(m.VerificationResult).where(
                m.VerificationResult.step_id == step_id
            ))
        )
    assert [row.status for row in results] == ["passed"]
    # The field that separates this from a self-report.
    assert results[0].evidence_available is True
    assert results[0].verifier_kind == "visual"
    assert results[0].observed_confidence == 0.95


async def test_a_pass_moves_the_guide_to_the_next_step(harness):
    session, step_id, claim_id, image_id = await checked(harness, verdict(confidence=0.92))
    await submit(harness, session, step_id, claim_id, image_id)
    await tick(harness.app)  # the check
    await tick(harness.app)  # the instruction it asked for

    current = await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    assert current.status_code == 200, current.text
    assert current.json()["data"]["step"]["id"] != step_id


# --- everything else ------------------------------------------------------


async def test_a_weak_answer_asks_instead_of_advancing(harness):
    session, step_id, claim_id, image_id = await checked(harness, verdict(confidence=0.7))
    await submit(harness, session, step_id, claim_id, image_id)
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, step_id)
        assert step.status != "verified"
        assert step.verified_at is None
        row = await db.scalar(select(m.VerificationResult).where(
            m.VerificationResult.step_id == step_id
        ))
    assert row.status == "inconclusive"
    # Still the user's step, still waiting on them.
    assert (await session_state(harness, session["id"]))["state"] == "awaiting_user_action"


async def test_a_screenshot_that_shows_nothing_done_is_a_mismatch(harness):
    session, step_id, claim_id, image_id = await checked(
        harness, verdict(step_complete=False, note="No prompt is visible.")
    )
    await submit(harness, session, step_id, claim_id, image_id)
    await tick(harness.app)

    async with harness.app.state.sessions() as db:
        row = await db.scalar(select(m.VerificationResult).where(
            m.VerificationResult.step_id == step_id
        ))
        step = await db.get(m.TaskStep, step_id)
    assert row.status == "mismatch"
    assert row.reason == "No prompt is visible."
    # Counted as an attempt, which is what eventually says the guide is stuck.
    assert step.attempt_count >= 1


async def test_the_step_is_still_offered_after_a_mismatch(harness):
    session, step_id, claim_id, image_id = await checked(
        harness, verdict(step_complete=False)
    )
    await submit(harness, session, step_id, claim_id, image_id)
    await tick(harness.app)
    current = await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    assert current.json()["data"]["step"]["id"] == step_id


# --- what the route refuses ----------------------------------------------


async def test_evidence_from_another_task_is_refused(harness):
    from tests.test_flow import create

    session, step_id, claim_id, _ = await checked(harness)
    elsewhere = await create(harness, goal="A different problem entirely, on another machine.")
    other_image = await share(
        harness,
        elsewhere.json()["data"]["task"],
        elsewhere.json()["data"]["session"],
    )
    response = await submit(harness, session, step_id, claim_id, other_image["id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_more_than_one_screenshot_is_refused(harness):
    session, step_id, claim_id, image_id = await checked(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{step_id}/verifications",
        json={
            "expected_version": session["state_version"],
            "claim_id": claim_id,
            "evidence_ids": [image_id, image_id],
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


async def test_a_deleted_screenshot_cannot_verify_anything(harness):
    session, step_id, claim_id, image_id = await checked(harness)
    assert (await harness.client.delete(PREFIX + f"/screenshots/{image_id}")).status_code in (
        200, 202
    )
    # Deleting evidence moves the session on, as it should: read it back, so the
    # request is refused for the deletion rather than for a stale version.
    session = await session_state(harness, session["id"])
    response = await submit(harness, session, step_id, claim_id, image_id)
    assert response.status_code == 410
    assert response.json()["error"]["code"] in {"data_deleted", "media_expired"}


async def test_the_users_word_still_works_exactly_as_before(harness):
    """The self-report arm is untouched: it records `user_reported`, awards no
    badge, and answers 200 rather than queueing anything."""
    session, step_id, claim_id, _ = await checked(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{step_id}/verifications",
        json={
            "expected_version": session["state_version"],
            "claim_id": claim_id,
            "self_report": "I did that.",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["verification"]["status"] == "user_reported"
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.TaskStep, step_id)).verified_at is None
