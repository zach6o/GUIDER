"""Saying the guidance was wrong.

Three kinds of feedback are opinions. The fourth, `incorrect_guidance`, is the
only thing that ever tells Guider a verdict it reached by itself was wrong, and
doc 05 gives it teeth: the pointer is withdrawn, the pass is downgraded, watching
is revoked and the session blocks. These tests hold both halves — that the
expensive kind does all of that, and that the cheap kinds do none of it.
"""

from uuid import uuid4

from sqlalchemy import select

from app import models as m
from tests.test_flow import PREFIX
from tests.test_instructions import session_state, started
from tests.test_observation import observe, verdict, watching
from tests.test_self_report import claim, self_report


async def send(harness, session, kind, step_id=None, text="", key=None, **body):
    payload = {"expected_version": session["state_version"], "kind": kind, "text": text, **body}
    if step_id:
        payload["step_id"] = step_id
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/feedback",
        json=payload,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


async def rows(harness, model, **where):
    async with harness.app.state.sessions() as db:
        query = select(model)
        for column, value in where.items():
            query = query.where(getattr(model, column) == value)
        return list(await db.scalars(query))


# --- the kinds that change nothing ----------------------------------------


async def test_an_opinion_is_recorded_and_the_guide_carries_on(harness):
    _, session, current = await started(harness)
    response = await send(harness, session, "helpful", current["step"]["id"], "That worked.")
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["verification_withdrawn"] is False
    assert body["session"]["state"] == "awaiting_user_action"

    saved = await rows(harness, m.UserFeedback)
    assert [(one.kind, one.text, one.status) for one in saved] == [
        ("helpful", "That worked.", "received")
    ]
    # The pointer is untouched: an opinion is not a correction.
    instructions = await rows(harness, m.Instruction, session_id=session["id"])
    assert [one.status for one in instructions] == ["ready"]


async def test_a_privacy_concern_does_not_block_the_session(harness):
    _, session, _ = await started(harness)
    response = await send(harness, session, "privacy_concern", text="I would rather not share.")
    assert response.status_code == 201, response.text
    assert response.json()["data"]["session"]["state"] == "awaiting_user_action"


# --- incorrect guidance ---------------------------------------------------


async def test_incorrect_guidance_blocks_and_withdraws_the_pointer(harness):
    _, session, current = await started(harness)
    before = session["control_epoch"]
    response = await send(
        harness, session, "incorrect_guidance", current["step"]["id"], "That button is not there."
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["session"]["state"] == "blocked"
    assert body["session"]["control_epoch"] > before

    instructions = await rows(harness, m.Instruction, session_id=session["id"])
    assert [one.status for one in instructions] == ["invalidated"]
    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
        # The checkpoint is what a later resume returns to.
        assert row.checkpoint_state == "awaiting_user_action"
        assert row.current_step_id is None


async def test_it_says_which_step_was_wrong(harness):
    _, session, _ = await started(harness)
    response = await send(harness, session, "incorrect_guidance", text="Something was off.")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    # Nothing was recorded and nothing blocked on a report that named no step.
    assert await rows(harness, m.UserFeedback) == []
    assert (await session_state(harness, session["id"]))["state"] == "awaiting_user_action"


async def test_a_pass_the_user_contradicts_stops_being_a_pass(harness):
    session, current = await watching(harness, verdict(confidence=0.93))
    step_id = current["step"]["id"]
    assert (await observe(harness, session)).json()["data"]["decision"] == "advance"

    session = await session_state(harness, session["id"])
    response = await send(harness, session, "incorrect_guidance", step_id, "It never opened.")
    assert response.status_code == 201, response.text
    assert response.json()["data"]["verification_withdrawn"] is True

    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, step_id)
        # Back to work, with no badge claiming otherwise.
        assert step.status == "pending"
        assert step.verified_at is None
    results = await rows(harness, m.VerificationResult, step_id=step_id)
    assert [one.status for one in results] == ["mismatch"]

    # The confidence that produced the wrong advance is kept on the feedback row,
    # because the verification it came from expires and the finding should not.
    saved = await rows(harness, m.UserFeedback)
    assert len(saved) == 1
    assert saved[0].observed_confidence == 0.93
    assert saved[0].verification_id == results[0].id


async def test_watching_is_revoked_when_guidance_is_called_wrong(harness):
    session, current = await watching(harness, verdict(confidence=0.5))
    await observe(harness, session)
    session = await session_state(harness, session["id"])
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.GuideSession, session["id"])).observation_active is True

    response = await send(
        harness, session, "incorrect_guidance", current["step"]["id"], "Wrong window."
    )
    assert response.status_code == 201, response.text
    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
        assert row.observation_active is False
        assert row.observation_mode == "screenshot_only"
    stopped = [
        one.type
        for one in await rows(harness, m.GuidanceEvent, session_id=session["id"])
        if one.type == "observation.stopped"
    ]
    assert stopped == ["observation.stopped"]


async def test_a_self_report_is_not_withdrawn_by_the_user_contradicting_guider(harness):
    """The user is disagreeing with Guider, not with themselves. Their own report
    stands; the session still blocks, because the guidance was still wrong."""
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    claimed = await claim(harness, session, step_id)
    session = await session_state(harness, session["id"])
    assert (await self_report(harness, session, step_id, claimed["claim_id"])).status_code == 200

    session = await session_state(harness, session["id"])
    response = await send(
        harness, session, "incorrect_guidance", step_id, "The next step is wrong."
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["verification_withdrawn"] is False
    results = await rows(harness, m.VerificationResult, step_id=step_id)
    assert [one.status for one in results] == ["user_reported"]
    assert response.json()["data"]["session"]["state"] == "blocked"


# --- the ordinary route obligations ---------------------------------------


async def test_a_replayed_report_does_not_block_twice(harness):
    _, session, current = await started(harness)
    key = uuid4()
    first = await send(
        harness, session, "incorrect_guidance", current["step"]["id"], "No.", key=key
    )
    assert first.status_code == 201, first.text
    again = await send(
        harness, session, "incorrect_guidance", current["step"]["id"], "No.", key=key
    )
    assert again.status_code == 201
    assert again.json()["data"]["feedback_id"] == first.json()["data"]["feedback_id"]
    assert len(await rows(harness, m.UserFeedback)) == 1
    epochs = [
        one.payload.get("control_epoch")
        for one in await rows(harness, m.GuidanceEvent, session_id=session["id"])
        if one.type == "session.state_changed" and one.payload.get("to") == "blocked"
    ]
    assert len(epochs) == 1


async def test_a_stale_version_is_refused(harness):
    _, session, current = await started(harness)
    stale = dict(session, state_version=session["state_version"] - 1)
    response = await send(harness, stale, "incorrect_guidance", current["step"]["id"], "No.")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_version"


async def test_another_owner_cannot_report_on_this_session(harness):
    _, session, current = await started(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/feedback",
        json={
            "expected_version": session["state_version"],
            "kind": "incorrect_guidance",
            "step_id": current["step"]["id"],
        },
        headers={
            "Idempotency-Key": str(uuid4()),
            "Authorization": f"Bearer {harness.token('f2bf182e-f619-492b-a1cc-c10cf660ca64')}",
        },
    )
    assert response.status_code == 404
