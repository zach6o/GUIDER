"""What happens when two of the user's requests arrive at once.

Doc 20's risk table has one line for this: today's row locks are no-ops on
SQLite and the engine depends on them. Until now one test held that line — two
plan confirmations racing — which proved the lock exists and nothing about the
paths a guide actually runs through.

Every test here races real routes against each other on PostgreSQL and asserts
the invariant rather than the winner. Which request wins is a scheduling detail;
that exactly one does, that the loser is refused rather than silently applied,
and that no record ends up describing two histories at once, are the product's
promises.

They skip on SQLite, which ignores `SELECT ... FOR UPDATE` and would report
green while proving nothing.
"""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from app import models as m
from tests.conftest import ALICE, on_postgres
from tests.test_flow import PREFIX
from tests.test_instructions import act, session_state, started
from tests.test_observation import observe, verdict, watching
from tests.test_self_report import advance, claim, self_report


def codes(*responses) -> list[int]:
    """Status codes, sorted, with exceptions surfaced rather than swallowed."""
    for response in responses:
        assert not isinstance(response, BaseException), response
    return sorted(response.status_code for response in responses)


async def counts(harness, model, **where) -> int:
    async with harness.app.state.sessions() as db:
        query = select(func.count()).select_from(model)
        for column, value in where.items():
            query = query.where(getattr(model, column) == value)
        return await db.scalar(query)


# --- two of the same thing ------------------------------------------------


@on_postgres
async def test_one_step_cannot_be_claimed_twice_at_once(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    first, second = await asyncio.gather(
        act(harness, session, step_id, "claim", statement="Done."),
        act(harness, session, step_id, "claim", statement="Done."),
        return_exceptions=True,
    )
    # The loser is refused for acting on a version that no longer exists, not
    # quietly accepted into a second claim.
    assert codes(first, second) == [200, 409]
    assert await counts(harness, m.CompletionClaim, step_id=step_id) == 1


@on_postgres
async def test_ten_simultaneous_claims_produce_one(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    results = await asyncio.gather(
        *(act(harness, session, step_id, "claim", statement="Done.") for _ in range(10)),
        return_exceptions=True,
    )
    assert codes(*results) == [200] + [409] * 9
    assert await counts(harness, m.CompletionClaim, step_id=step_id) == 1


@on_postgres
async def test_a_claim_and_a_skip_cannot_both_land(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    claimed, skipped = await asyncio.gather(
        act(harness, session, step_id, "claim", statement="Done."),
        act(harness, session, step_id, "skip", reason="not_applicable"),
        return_exceptions=True,
    )
    assert codes(claimed, skipped) == [200, 409]
    async with harness.app.state.sessions() as db:
        step = await db.get(m.TaskStep, step_id)
        # One outcome, whichever it was. Never a step both skipped and claimed.
        assert step.status in {"user_claimed", "skipped"}


@on_postgres
async def test_one_claim_cannot_be_reported_done_twice(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    claimed = await claim(harness, session, step_id)
    session = await session_state(harness, session["id"])
    first, second = await asyncio.gather(
        self_report(harness, session, step_id, claimed["claim_id"]),
        self_report(harness, session, step_id, claimed["claim_id"]),
        return_exceptions=True,
    )
    assert codes(first, second) == [200, 409]
    assert await counts(harness, m.VerificationResult, step_id=step_id) == 1


# --- the user and the observer at the same time ---------------------------


@on_postgres
async def test_a_self_report_and_an_advance_cannot_both_settle_a_step(harness):
    session, current = await watching(harness, verdict(confidence=0.95))
    step_id = current["step"]["id"]
    claimed = await claim(harness, session, step_id)
    session = await session_state(harness, session["id"])

    reported, observed = await asyncio.gather(
        self_report(harness, session, step_id, claimed["claim_id"]),
        observe(harness, session),
        return_exceptions=True,
    )
    assert codes(reported, observed) == [200, 409]
    # Exactly one result, so the step is either checked or reported — never both,
    # which would let a summary count one step twice.
    assert await counts(harness, m.VerificationResult, step_id=step_id) == 1


@on_postgres
async def test_stopping_beats_a_frame_that_is_already_in_flight(harness):
    session, current = await watching(harness, verdict(confidence=0.99))
    step_id = current["step"]["id"]
    stopped, observed = await asyncio.gather(
        harness.client.delete(PREFIX + f"/sessions/{session['id']}/observation"),
        observe(harness, session),
        return_exceptions=True,
    )
    assert not isinstance(stopped, BaseException), stopped
    assert stopped.status_code == 200
    async with harness.app.state.sessions() as db:
        row = await db.get(m.GuideSession, session["id"])
        assert row.observation_active is False
        step = await db.get(m.TaskStep, step_id)
        if isinstance(observed, BaseException) or observed.status_code != 200:
            # The ordinary case: the tick lost, so nothing it would have done
            # happened — no verification, no advance, no spent budget.
            assert step.status != "verified"
            assert await counts(harness, m.VerificationResult, step_id=step_id) == 0
        else:
            # The tick landed first. Stopping still switched watching off, and
            # the frame is the last one that will ever be looked at.
            assert row.frames_observed == 1


# --- records that describe one history ------------------------------------


@on_postgres
async def test_one_session_ends_once(harness):
    _, session, _ = await started(harness)
    # Every step reported, so the plan is out and finishing is allowed at all.
    while await advance(harness, session["id"]):
        pass
    session = await session_state(harness, session["id"])

    async def finish():
        return await harness.client.post(
            PREFIX + f"/sessions/{session['id']}/completion",
            json={
                "expected_version": session["state_version"],
                "outcome": "user_reported",
                "self_report": "Done.",
            },
            headers={"Idempotency-Key": str(uuid4())},
        )

    first, second = await asyncio.gather(finish(), finish(), return_exceptions=True)
    assert 200 in codes(first, second)
    # One summary, whatever the second request was told: a task has one ending.
    assert await counts(harness, m.SessionSummary, session_id=session["id"]) == 1


@on_postgres
async def test_one_key_replayed_at_the_same_moment_does_one_thing(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    key = str(uuid4())

    async def send():
        return await harness.client.post(
            PREFIX + f"/sessions/{session['id']}/steps/{step_id}/claim",
            json={"expected_version": session["state_version"], "statement": "Done."},
            headers={"Idempotency-Key": key},
        )

    first, second = await asyncio.gather(send(), send(), return_exceptions=True)
    assert codes(first, second) == [200, 200]
    # A replay returns the first answer rather than performing a second claim.
    assert first.json()["data"]["claim_id"] == second.json()["data"]["claim_id"]
    assert await counts(harness, m.CompletionClaim, step_id=step_id) == 1


@on_postgres
async def test_the_event_stream_stays_gapless_under_concurrent_writers(harness):
    """A client resumes at a cursor, so a duplicated or skipped sequence is a
    client that misses an instruction. The unique constraint refuses duplicates;
    this checks the numbers a reader actually sees."""
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    await asyncio.gather(
        *(act(harness, session, step_id, "claim", statement="Done.") for _ in range(6)),
        return_exceptions=True,
    )
    async with harness.app.state.sessions() as db:
        sequences = list(
            await db.scalars(
                select(m.GuidanceEvent.sequence)
                .where(m.GuidanceEvent.session_id == session["id"])
                .order_by(m.GuidanceEvent.sequence)
            )
        )
    assert sequences == list(range(1, len(sequences) + 1))


@on_postgres
async def test_two_owners_do_not_block_each_other(harness):
    """The lock is per owner, not global: one user's guide must not wait behind
    another's. Both of these succeed, which is the point."""
    _, session, current = await started(harness)
    other = harness.token("f2bf182e-f619-492b-a1cc-c10cf660ca64")
    mine, theirs = await asyncio.gather(
        act(harness, session, current["step"]["id"], "claim", statement="Done."),
        harness.client.post(
            PREFIX + "/tasks",
            json={
                "title": "Their own task",
                "goal": "Set up a project of their own on their own machine.",
                "category": "setup",
                "application_key": "vscode",
            },
            headers={"Idempotency-Key": str(uuid4()), "Authorization": f"Bearer {other}"},
        ),
        return_exceptions=True,
    )
    assert codes(mine, theirs) == [200, 201]
    assert await counts(harness, m.GuideTask, owner_id=ALICE) == 1
