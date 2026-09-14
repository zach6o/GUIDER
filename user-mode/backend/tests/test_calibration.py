"""The calibration report says what happened, and no more than that.

D05 has to decide whether 0.85 is the right line. That decision needs counts, and
counts are only useful if they are honest about what they are not: an advance
nobody complained about is unchallenged, never confirmed. These tests pin the
arithmetic and that distinction.
"""

from uuid import uuid4

from app.guide.calibration import Report, bucket_of, build, for_owner, merge, render
from tests.test_feedback import send
from tests.test_instructions import session_state
from tests.test_observation import observe, verdict, watching


def tick(decision, confidence, step="step-1"):
    return {
        "type": "observation.tick",
        "payload": {"decision": decision, "confidence": confidence, "step_id": step},
    }


def contradiction(confidence, step="step-1"):
    return {
        "type": "verification.contradicted",
        "payload": {"step_id": step, "confidence": confidence},
    }


def self_reported(step="step-1"):
    return {
        "type": "verification.completed",
        "payload": {"step_id": step, "passed": False, "status": "user_reported"},
    }


# --- the arithmetic -------------------------------------------------------


def test_buckets_are_five_hundredths_wide():
    assert bucket_of(0.0) == 0.0
    assert bucket_of(0.87) == 0.85
    assert bucket_of(0.85) == 0.85
    assert bucket_of(1.0) == 0.95


def test_decisions_are_counted_per_band():
    report = build([tick("advance", 0.91), tick("ask", 0.72), tick("wait", 0.3)])
    assert (report.ticks, report.advances, report.asks, report.waits) == (3, 1, 1, 1)
    assert report.buckets[0.90].advances == 1
    assert report.buckets[0.70].asks == 1
    assert report.buckets[0.30].waits == 1


def test_an_advance_nobody_challenged_is_not_a_confirmed_advance():
    report = build([tick("advance", 0.9), tick("advance", 0.95), contradiction(0.9)])
    assert report.advances == 2
    assert report.contradicted == 1
    # The word matters: one was reported wrong, the other was never checked.
    assert report.unchallenged == 1
    assert "silence is not confirmation" in render(report)


def test_an_answered_question_is_told_from_an_abandoned_one():
    answered = build([tick("ask", 0.7), self_reported()])
    assert (answered.asks_confirmed, answered.asks_unconfirmed) == (1, 0)

    asked_again = build([tick("ask", 0.7), tick("ask", 0.72), self_reported()])
    # Two questions, one answer: the first went unanswered.
    assert (asked_again.asks_confirmed, asked_again.asks_unconfirmed) == (1, 1)

    dropped = build([tick("ask", 0.7)])
    assert (dropped.asks_confirmed, dropped.asks_unconfirmed) == (0, 1)


def test_a_question_the_observer_resolved_itself_is_not_a_user_answer():
    report = build([
        tick("ask", 0.7),
        {"type": "verification.completed", "payload": {"step_id": "step-1", "passed": True}},
    ])
    assert (report.asks_confirmed, report.asks_unconfirmed) == (0, 0)


def test_moving_the_line_is_reported_as_what_it_would_have_done():
    report = build([
        tick("advance", 0.86), tick("advance", 0.97), tick("ask", 0.8), contradiction(0.86),
    ])
    raising = report.threshold_effect(0.90)
    assert raising["advances_kept"] == 1
    assert raising["known_bad_excluded"] == 1
    lowering = report.threshold_effect(0.80)
    assert lowering["advances_kept"] == 2
    # The ask at 0.80 would have advanced instead, which is the cost of lowering.
    assert lowering["asks_promoted"] == 1


def test_merging_keeps_the_session_count_and_the_buckets():
    total = merge([build([tick("advance", 0.9)]), build([tick("advance", 0.9), tick("wait", 0.1)])])
    assert total.sessions == 2
    assert total.ticks == 3
    assert total.buckets[0.90].advances == 2


def test_an_empty_report_renders_without_pretending_to_know_anything():
    text = render(Report())
    assert "ticks 0" in text
    assert "advance 0.85" in text


# --- against a real session ----------------------------------------------


async def test_a_watched_session_and_a_correction_reach_the_report(harness):
    session, current = await watching(harness, verdict(confidence=0.93))
    step_id = current["step"]["id"]
    assert (await observe(harness, session)).json()["data"]["decision"] == "advance"
    session = await session_state(harness, session["id"])
    assert (
        await send(harness, session, "incorrect_guidance", step_id, "It never opened.", key=uuid4())
    ).status_code == 201

    async with harness.app.state.sessions() as db:
        report = await for_owner(db, "54d332b0-9948-42c8-94dd-11a913c79719")
    assert report.advances == 1
    assert report.contradicted == 1
    assert report.unchallenged == 0
    assert report.buckets[0.90].contradicted == 1


async def test_owners_do_not_see_each_other_in_the_report(harness):
    session, _ = await watching(harness, verdict(confidence=0.93))
    await observe(harness, session)
    async with harness.app.state.sessions() as db:
        other = await for_owner(db, "f2bf182e-f619-492b-a1cc-c10cf660ca64")
    assert other.ticks == 0
