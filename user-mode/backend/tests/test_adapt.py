"""Guidance that follows the screen instead of the list.

The selector is deliberately a pure function over one belief, so the table of
what each screen means is the whole rule and can be read in one place. What the
tests hold beyond that table is the boundary: adapting changes words, and the one
move that changes the user's record asks first.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.guide.adapt import OFF_TRACK_LIMIT, Decision, decide
from app.guide.context import ACT_AT
from tests.test_context import StubContextObserver, seen, tick, watching_context
from tests.test_flow import PREFIX
from tests.test_instructions import session_state


def steps(*titles) -> list[m.TaskStep]:
    return [
        m.TaskStep(id=f"step-{index}", ordinal=index + 2, title=title)
        for index, title in enumerate(titles)
    ]


def current_step() -> m.TaskStep:
    return m.TaskStep(id="step-current", ordinal=1, title="Open the terminal")


# --- the table ------------------------------------------------------------


@pytest.mark.parametrize(
    ("context", "action"),
    [
        (seen(stage="in_progress"), "none"),
        (seen(stage="step_satisfied"), "check"),
        (seen(stage="blocked_dialog", dialog="Allow access?"), "dialog"),
        (seen(stage="off_track"), "redirect"),
        (seen(stage="unreadable", confidence=0.0), "unreadable"),
        (seen(application_matches_expected=False, application="Discord"), "wrong_application"),
    ],
)
def test_each_screen_means_one_thing(context, action):
    assert decide(context, current_step(), steps("Later")).action == action


def test_being_somewhere_else_outranks_looking_finished():
    """A step cannot be satisfied on a screen that belongs to another
    application. The wrong window is the thing to say."""
    context = seen(stage="step_satisfied", application_matches_expected=False)
    assert decide(context, current_step(), []).action == "wrong_application"


def test_only_a_redirect_or_a_dialog_costs_a_new_instruction():
    for context in (seen(stage="off_track"), seen(stage="blocked_dialog")):
        assert decide(context, current_step(), steps("Later")).reinstruct is True
    for context in (seen(stage="in_progress"), seen(stage="step_satisfied")):
        assert decide(context, current_step(), steps("Later")).reinstruct is False


# --- skipping forward -----------------------------------------------------


def test_a_later_step_that_is_done_offers_everything_up_to_it():
    later = steps("Install it", "Open the file", "Run it")
    context = seen(stage="later_step_satisfied", satisfied_later_index=1, confidence=0.95)
    decision = decide(context, current_step(), later)
    assert decision.action == "offer_skip"
    # Up to and including the one the screen satisfies, and no further.
    assert decision.skippable == ("step-0", "step-1")


def test_a_weak_belief_never_offers_to_skip():
    later = steps("Install it")
    context = seen(stage="later_step_satisfied", satisfied_later_index=0, confidence=ACT_AT - 0.01)
    assert decide(context, current_step(), later).action == "none"


def test_an_index_that_names_no_step_offers_nothing():
    context = seen(stage="later_step_satisfied", satisfied_later_index=7, confidence=0.99)
    assert decide(context, current_step(), steps("Only one")).action == "none"


def test_the_offer_carries_no_authority_of_its_own():
    """A Decision is a proposal. Nothing in it settles a step — that takes the
    route, with the ids echoed back."""
    decision = Decision("offer_skip", skippable=("step-0",))
    assert decision.action == "offer_skip"
    assert not hasattr(decision, "apply")


# --- against a session ----------------------------------------------------


async def test_a_tick_says_what_the_guide_will_do_about_it(harness):
    session, _ = await watching_context(
        harness, seen(stage="off_track", application="Discord",
                      application_matches_expected=False)
    )
    body = (await tick(harness, session)).json()["data"]
    assert body["action"] == "wrong_application"
    assert "Discord" in body["message"]
    assert body["offer"] is None


async def test_being_off_track_repeatedly_is_a_guide_going_nowhere(harness):
    session, _ = await watching_context(harness)
    harness.app.state.context_observer = StubContextObserver(
        *[
            seen(stage="off_track", screen=f"somewhere else {index}")
            for index in range(OFF_TRACK_LIMIT)
        ]
    )
    for _ in range(OFF_TRACK_LIMIT):
        assert (await tick(harness, session)).status_code == 200
        session = await session_state(harness, session["id"])

    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
    assert row.stuck_since is not None


async def test_a_skip_forward_settles_only_what_the_user_was_shown(harness):
    session, current = await watching_context(harness)
    async with harness.app.state.sessions() as db:
        later = list(
            await db.scalars(select(m.TaskStep).where(m.TaskStep.ordinal > 1).order_by(
                m.TaskStep.ordinal
            ))
        )
    assert later, "the fixture plan should have later steps"

    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{current['step']['id']}/skip-forward",
        json={"expected_version": session["state_version"], "step_ids": [later[0].id]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    titles = [row["title"] for row in response.json()["data"]["steps"]]
    assert current["step"]["title"] in titles

    async with harness.app.state.sessions() as db:
        settled = await db.get(m.TaskStep, later[0].id)
        # Skipped, not verified and not reported done: nobody said they were.
        assert settled.status == "skipped"
        assert settled.verified_at is None
        assert await db.scalar(select(m.VerificationResult)) is None


async def test_a_step_behind_the_guide_cannot_be_skipped_forward(harness):
    session, current = await watching_context(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{current['step']['id']}/skip-forward",
        json={
            "expected_version": session["state_version"],
            "step_ids": [current["step"]["id"]],
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_a_blocked_step_is_never_settled_by_a_skip(harness):
    session, current = await watching_context(harness)
    async with harness.app.state.sessions() as db, db.begin():
        later = await db.scalar(
            select(m.TaskStep).where(m.TaskStep.ordinal == 2)
        )
        later.policy_disposition = "block"
        blocked_id = later.id

    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{current['step']['id']}/skip-forward",
        json={"expected_version": session["state_version"], "step_ids": [blocked_id]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "blocked_task"
