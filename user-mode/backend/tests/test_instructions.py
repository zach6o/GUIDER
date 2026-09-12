from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.errors import GuideError
from app.guide.guard import vet_instruction
from app.providers.base import InstructionContext, ProposedInstruction
from app.providers.fixture import FixtureProvider
from app.worker import tick
from tests.test_flow import PREFIX, create
from tests.test_planning import confirm, planned


async def session_state(harness, session_id):
    return (await harness.client.get(PREFIX + f"/sessions/{session_id}")).json()["data"]


async def started(harness):
    """A confirmed plan, started, with its first instruction published."""
    created, session, plan = await planned(harness)
    confirmed = (await confirm(harness, session, plan)).json()["data"]["session"]
    response = await harness.client.post(
        PREFIX + f"/sessions/{confirmed['id']}/start",
        json={"expected_version": confirmed["state_version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    await tick(harness.app)
    current = await session_state(harness, confirmed["id"])
    instruction = await harness.client.get(PREFIX + f"/sessions/{confirmed['id']}/instruction")
    return created, current, instruction.json()["data"]


async def act(harness, session, step_id, verb, **body):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/steps/{step_id}/{verb}",
        json={"expected_version": session["state_version"], **body},
        headers={"Idempotency-Key": str(uuid4())},
    )


# --- starting -------------------------------------------------------------


async def test_a_session_cannot_start_without_a_confirmed_plan(harness):
    _, session, _ = await planned(harness)
    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/start",
        json={"expected_version": session["state_version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_starting_publishes_the_first_instruction(harness):
    _, session, current = await started(harness)
    assert session["state"] == "awaiting_user_action"
    assert current["step"]["ordinal"] == 1
    assert current["step"]["status"] == "awaiting_user_action"
    assert current["instruction"]["version"] == 1
    assert current["instruction"]["what"]
    assert current["instruction"]["confirmation_hint"]
    assert session["current_step_id"] == current["step"]["id"]


async def test_the_instruction_route_is_owner_scoped(harness):
    _, session, _ = await started(harness)
    intruder = {"Authorization": f"Bearer {harness.token(owner=str(uuid4()))}"}
    response = await harness.client.get(
        PREFIX + f"/sessions/{session['id']}/instruction", headers=intruder
    )
    assert response.status_code in {401, 404}


# --- a claim is not a verification ---------------------------------------


async def test_a_claim_is_recorded_without_verifying_the_step(harness):
    _, session, current = await started(harness)
    response = await act(harness, session, current["step"]["id"], "claim", statement="Done that.")
    assert response.status_code == 200
    body = response.json()["data"]

    # The contract says so...
    assert body["verified"] is False
    # ...the step status says so...
    assert body["step"]["status"] == "user_claimed"
    assert body["step"]["verified_at"] is None
    # ...and the session has not moved on.
    assert body["session"]["state"] == "awaiting_user_action"
    assert body["session"]["current_step_id"] == current["step"]["id"]

    async with harness.app.state.sessions() as db:
        claim = await db.scalar(select(m.CompletionClaim))
        step = await db.get(m.TaskStep, current["step"]["id"])
    assert claim.statement == "Done that."
    assert claim.status == "user_claimed"
    assert claim.instruction_version == current["instruction"]["version"]
    assert step.status == "user_claimed"
    assert step.verified_at is None


async def test_claiming_records_an_event_marked_unverified(harness):
    _, session, current = await started(harness)
    await act(harness, session, current["step"]["id"], "claim")
    async with harness.app.state.sessions() as db:
        event = await db.scalar(
            select(m.GuidanceEvent).where(m.GuidanceEvent.type == "step.user_claimed")
        )
    assert event.payload["verified"] is False


async def test_claiming_twice_supersedes_the_earlier_claim(harness):
    _, session, current = await started(harness)
    await act(harness, session, current["step"]["id"], "claim", statement="First.")
    session = await session_state(harness, session["id"])
    await act(harness, session, current["step"]["id"], "claim", statement="Actually now.")
    async with harness.app.state.sessions() as db:
        claims = list(
            await db.scalars(select(m.CompletionClaim).order_by(m.CompletionClaim.created_at))
        )
    assert [claim.status for claim in claims] == ["superseded", "user_claimed"]


async def test_a_claim_needs_a_current_instruction(harness):
    created, session, plan = await planned(harness)
    confirmed = (await confirm(harness, session, plan)).json()["data"]["session"]
    async with harness.app.state.sessions() as db:
        step = await db.scalar(select(m.TaskStep).order_by(m.TaskStep.ordinal))
    response = await act(harness, confirmed, step.id, "claim")
    assert response.status_code == 409


# --- skipping -------------------------------------------------------------


async def test_skipping_moves_to_the_next_step(harness):
    _, session, current = await started(harness)
    response = await act(
        harness, session, current["step"]["id"], "skip", reason="already_done"
    )
    assert response.status_code == 200
    assert response.json()["data"]["step"]["status"] == "skipped"
    await tick(harness.app)

    following = (
        await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    ).json()["data"]
    assert following["step"]["ordinal"] == 2
    assert following["instruction"]["id"] != current["instruction"]["id"]


async def test_the_superseded_instruction_is_no_longer_current(harness):
    _, session, current = await started(harness)
    await act(harness, session, current["step"]["id"], "skip", reason="cannot_do")
    await tick(harness.app)
    async with harness.app.state.sessions() as db:
        statuses = {
            row.id: row.status for row in await db.scalars(select(m.Instruction))
        }
    assert statuses[current["instruction"]["id"]] == "superseded"
    assert list(statuses.values()).count("ready") == 1


async def test_running_out_of_steps_does_not_claim_success(harness):
    _, session, current = await started(harness)
    for _ in range(3):
        state = await session_state(harness, session["id"])
        instruction = await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
        if instruction.status_code != 200:
            break
        step_id = instruction.json()["data"]["step"]["id"]
        await act(harness, state, step_id, "skip", reason="not_applicable")
        await tick(harness.app)

    final = await session_state(harness, session["id"])
    # No steps left, but nothing was verified, so the task is not complete.
    assert final["state"] == "awaiting_user_action"
    assert final["outcome"] is None
    async with harness.app.state.sessions() as db:
        kinds = list(await db.scalars(select(m.GuidanceEvent.type)))
    assert "plan.steps_exhausted" in kinds


# --- the guard on an instruction -----------------------------------------


def instruction(**overrides) -> ProposedInstruction:
    return ProposedInstruction.model_validate(
        {
            "what": "Read the error text above the prompt.",
            "where": "In the terminal panel.",
            "why": "The message names the missing package.",
            "confirmation_hint": "The error text is visible.",
            "cannot_find_hint": "Scroll up a little.",
        }
        | overrides
    )


def test_a_restricted_instruction_is_refused_rather_than_softened():
    with pytest.raises(GuideError) as error:
        vet_instruction(instruction(what="Delete the build folder."))
    assert error.value.status == 409
    assert error.value.body["code"] == "action_requires_review"


def test_a_restricted_fallback_is_refused_too():
    with pytest.raises(GuideError):
        vet_instruction(instruction(cannot_find_hint="Otherwise uninstall the package."))


def test_descriptive_instruction_fields_are_not_matched():
    assert vet_instruction(instruction(why="The installer removed it earlier."))


def test_an_ordinary_instruction_passes():
    assert vet_instruction(instruction()).what


async def test_the_fixture_writer_invents_nothing():
    context = InstructionContext(
        goal="Why won't Python run?",
        application_key="vscode",
        title="Open the terminal",
        action="Open the integrated terminal.",
        expected_result="A shell prompt appears.",
        fallback="Use the View menu.",
        explanation="The interpreter reports there.",
        ordinal=1,
        total_steps=3,
    )
    written = await FixtureProvider().instruct(context)
    assert written.what == context.action
    assert written.confirmation_hint == context.expected_result
    assert written.cannot_find_hint == context.fallback


async def test_a_blocked_step_is_never_handed_out(harness):
    _, session, plan = await planned(harness)
    async with harness.app.state.sessions() as db, db.begin():
        first = await db.scalar(select(m.TaskStep).order_by(m.TaskStep.ordinal))
        first.policy_disposition = "block"
    confirmed = (await confirm(harness, session, plan)).json()["data"]["session"]
    await harness.client.post(
        PREFIX + f"/sessions/{confirmed['id']}/start",
        json={"expected_version": confirmed["state_version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    await tick(harness.app)
    current = (
        await harness.client.get(PREFIX + f"/sessions/{confirmed['id']}/instruction")
    ).json()["data"]
    assert current["step"]["ordinal"] == 2


async def test_creating_a_task_still_works(harness):
    assert (await create(harness)).status_code == 201
