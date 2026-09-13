"""How a task ends, and what the record says about it.

The distinction every other part of this system maintains has one last place to
be lost: the summary. `achieved` means evidence checked every required step.
Anything resting on the user's own word ends `user_reported` and says so, in the
outcome, in the lists, and in the prose.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.worker import tick
from tests.test_flow import PREFIX
from tests.test_instructions import act, session_state, started
from tests.test_observation import StubObserver, frame, verdict
from tests.test_replan import watching
from tests.test_self_report import advance, claim, self_report


async def finish(harness, session, outcome="user_reported", **body):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/completion",
        json={"expected_version": session["state_version"], "outcome": outcome, **body},
        headers={"Idempotency-Key": str(uuid4())},
    )


async def summary_of(harness, session_id):
    return await harness.client.get(PREFIX + f"/sessions/{session_id}/summary")


async def observe_once(harness, session, observer):
    harness.app.state.observer = observer
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observe",
        json={
            "expected_version": session["state_version"],
            "image_base64": frame(),
            "admitted_at": m.now().isoformat(),
        },
    )


async def all_reported(harness):
    """A plan the user worked through and reported themselves, start to end."""
    _, session, _ = await started(harness)
    while await advance(harness, session["id"]):
        pass
    return await session_state(harness, session["id"])


async def all_verified(harness):
    """A plan where an observer checked every step."""
    _, session, _ = await started(harness)
    session = await watching(harness, session)
    for _ in range(3):
        current = await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
        if current.status_code != 200:
            break
        session = await session_state(harness, session["id"])
        response = await observe_once(
            harness, session, StubObserver(verdict(step_complete=True, confidence=0.96))
        )
        assert response.status_code == 200, response.text
        await tick(harness.app)
    return await session_state(harness, session["id"])


# --- what each ending means ----------------------------------------------


async def test_a_self_reported_task_ends_user_reported_and_says_so(harness):
    session = await all_reported(harness)
    response = await finish(harness, session, "user_reported")
    assert response.status_code == 200, response.text
    body = response.json()["data"]

    assert body["session"]["outcome"] == "user_reported"
    assert body["session"]["state"] == "completed"
    assert body["summary"]["verified_steps"] == []
    assert len(body["summary"]["unverified_steps"]) == 3
    assert "told Guider" in body["summary"]["text"]
    assert "your own account" in body["summary"]["text"]


async def test_achieved_is_refused_when_nothing_was_checked(harness):
    session = await all_reported(harness)
    response = await finish(harness, session, "achieved")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verification_required"

    current = await session_state(harness, session["id"])
    assert current["state"] == "awaiting_user_action"
    assert current["outcome"] is None


async def test_achieved_is_allowed_when_evidence_checked_every_step(harness):
    session = await all_verified(harness)
    response = await finish(harness, session, "achieved")
    assert response.status_code == 200, response.text
    body = response.json()["data"]

    assert body["session"]["outcome"] == "achieved"
    assert len(body["summary"]["verified_steps"]) == 3
    assert body["summary"]["unverified_steps"] == []
    assert "checked on screen" in body["summary"]["text"]
    assert "Every required step was checked." in body["summary"]["text"]


async def test_the_two_kinds_of_step_are_kept_apart(harness):
    """The exit gate: one checked step and one reported step, told apart."""
    _, session, current = await started(harness)
    session = await watching(harness, session)
    assert (
        await observe_once(
            harness, session, StubObserver(verdict(step_complete=True, confidence=0.97))
        )
    ).status_code == 200
    await tick(harness.app)
    checked = current["step"]["id"]

    second = await advance(harness, session["id"])  # the user's own word
    third = await advance(harness, session["id"])
    session = await session_state(harness, session["id"])
    body = (await finish(harness, session, "user_reported")).json()["data"]

    assert body["summary"]["verified_steps"] == [checked]
    assert set(body["summary"]["unverified_steps"]) == {second["id"], third["id"]}
    assert "1 was checked on screen." in body["summary"]["text"]
    assert "2 you told Guider were done" in body["summary"]["text"]


async def test_a_skipped_step_is_named_rather_than_counted_away(harness):
    _, session, current = await started(harness)
    await act(harness, session, current["step"]["id"], "skip", reason="not_applicable")
    await tick(harness.app)
    while await advance(harness, session["id"]):
        pass

    session = await session_state(harness, session["id"])
    body = (await finish(harness, session, "user_reported")).json()["data"]
    assert any("was skipped" in note for note in body["summary"]["corrections"])
    assert current["step"]["id"] in body["summary"]["unverified_steps"]


# --- refusals -------------------------------------------------------------


async def test_a_task_with_open_steps_cannot_be_reported_finished(harness):
    _, session, _ = await started(harness)
    response = await finish(harness, session, "user_reported")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verification_required"


async def test_finishing_twice_returns_the_same_ending(harness):
    session = await all_reported(harness)
    key = {"Idempotency-Key": str(uuid4())}
    body = {"expected_version": session["state_version"], "outcome": "user_reported"}
    path = PREFIX + f"/sessions/{session['id']}/completion"
    first = await harness.client.post(path, json=body, headers=key)
    second = await harness.client.post(path, json=body, headers=key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]

    async with harness.app.state.sessions() as db:
        summaries = list(await db.scalars(select(m.SessionSummary)))
    assert len(summaries) == 1


async def test_a_finished_task_cannot_be_finished_again_with_a_new_key(harness):
    session = await all_reported(harness)
    assert (await finish(harness, session, "user_reported")).status_code == 200
    session = await session_state(harness, session["id"])
    response = await finish(harness, session, "achieved")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_a_stale_version_cannot_finish_a_task(harness):
    session = await all_reported(harness)
    stale = {**session, "state_version": session["state_version"] - 1}
    assert (await finish(harness, stale, "user_reported")).status_code == 409


# --- reading it back ------------------------------------------------------


async def test_the_summary_is_not_available_before_the_task_ends(harness):
    _, session, _ = await started(harness)
    response = await summary_of(harness, session["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_terminal"


async def test_stopping_still_leaves_something_to_read(harness):
    _, session, _ = await started(harness)
    await advance(harness, session["id"])
    stopped = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/stop",
        json={"reason": "user"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert stopped.status_code == 200

    summary = (await summary_of(harness, session["id"])).json()["data"]
    assert summary["outcome"] == "stopped"
    assert "You stopped this task." in summary["text"]
    assert len(summary["unverified_steps"]) >= 1
    assert summary["verified_steps"] == []


async def test_the_summary_is_owner_scoped(harness):
    session = await all_reported(harness)
    await finish(harness, session, "user_reported")
    intruder = {"Authorization": f"Bearer {harness.token(owner=str(uuid4()))}"}
    response = await harness.client.get(
        PREFIX + f"/sessions/{session['id']}/summary", headers=intruder
    )
    assert response.status_code in {401, 404}


async def test_history_shows_how_each_task_ended(harness):
    session = await all_reported(harness)
    await finish(harness, session, "user_reported")
    history = (await harness.client.get(PREFIX + "/sessions")).json()["data"]
    entry = [item for item in history["items"] if item["session"]["id"] == session["id"]][0]
    assert entry["session"]["outcome"] == "user_reported"
    assert entry["session"]["state"] == "completed"


async def test_a_blocked_step_stops_a_task_being_called_finished(harness):
    """A required step Guider refused to instruct is not something the user can
    report their way past."""
    _, session, current = await started(harness)
    async with harness.app.state.sessions() as db, db.begin():
        plan = await db.scalar(select(m.TaskPlan))
        remaining = list(
            await db.scalars(
                select(m.TaskStep)
                .where(m.TaskStep.plan_id == plan.id)
                .order_by(m.TaskStep.ordinal)
            )
        )
        remaining[-1].policy_disposition = "block"
    claimed = await claim(harness, session, current["step"]["id"])
    session = await session_state(harness, session["id"])
    await self_report(harness, session, current["step"]["id"], claimed["claim_id"])
    await tick(harness.app)
    session = await session_state(harness, session["id"])

    response = await finish(harness, session, "user_reported")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verification_required"


async def test_a_blocked_step_is_named_in_the_summary_of_a_stopped_task(harness):
    _, session, _ = await started(harness)
    async with harness.app.state.sessions() as db, db.begin():
        plan = await db.scalar(select(m.TaskPlan))
        steps = list(
            await db.scalars(
                select(m.TaskStep)
                .where(m.TaskStep.plan_id == plan.id)
                .order_by(m.TaskStep.ordinal)
            )
        )
        steps[-1].policy_disposition = "block"
    await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/stop",
        json={"reason": "user"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    summary = (await summary_of(harness, session["id"])).json()["data"]
    assert any("needs separate review" in note for note in summary["corrections"])
    assert summary["next_action"]


@pytest.mark.parametrize("outcome", ["achieved", "user_reported"])
async def test_a_session_without_a_confirmed_plan_cannot_finish(harness, outcome):
    created = await harness.client.post(
        PREFIX + "/tasks",
        json={"goal": "Work out why this fails", "category": "debug", "application_key": "vscode"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    session = created.json()["data"]["session"]
    response = await finish(harness, session, outcome)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
