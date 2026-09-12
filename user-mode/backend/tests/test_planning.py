from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models as m
from app.guide.guard import NEEDS_REVIEW, step_policy
from app.providers.base import PlanContext, ProposedPlan, ProposedStep
from app.worker import tick
from tests.test_flow import PREFIX, create

GOAL = {"goal": "Why won't Python run?", "category": "debug", "application_key": "powershell"}


async def request_plan(harness, created, key=None, **overrides):
    data = created.json()["data"]
    session_id = data["session"]["id"]
    # Always read the live version: a replan follows an earlier state change.
    current = (await harness.client.get(PREFIX + f"/sessions/{session_id}")).json()["data"]
    return await harness.client.post(
        PREFIX + f"/tasks/{data['task']['id']}/plans",
        json={
            "session_id": session_id,
            "expected_version": current["state_version"],
            **overrides,
        },
        headers={"Idempotency-Key": key or str(uuid4())},
    )


async def planned(harness):
    """A task whose plan has been produced and is awaiting confirmation."""
    created = await create(harness)
    await request_plan(harness, created)
    await tick(harness.app)
    session_id = created.json()["data"]["session"]["id"]
    session = (await harness.client.get(PREFIX + f"/sessions/{session_id}")).json()["data"]
    async with harness.app.state.sessions() as db:
        plan = await db.scalar(select(m.TaskPlan).where(m.TaskPlan.session_id == session_id))
    return created, session, plan


async def confirm(harness, session, plan, key=None, **overrides):
    body = {
        "expected_version": session["state_version"],
        "plan_version": plan.version,
        **overrides,
    }
    return await harness.client.post(
        PREFIX + f"/plans/{plan.id}/confirm",
        json=body,
        headers={"Idempotency-Key": key or str(uuid4())},
    )


# --- requesting a plan ----------------------------------------------------


async def test_requesting_a_plan_queues_work_and_moves_to_analyzing(harness):
    created = await create(harness)
    response = await request_plan(harness, created)
    assert response.status_code == 202
    body = response.json()["data"]
    assert body["session"]["state"] == "analyzing"
    async with harness.app.state.sessions() as db:
        operation = await db.scalar(select(m.OperationRow))
    assert (operation.kind, operation.status) == ("plan", "queued")


async def test_worker_publishes_a_plan_for_confirmation(harness):
    _, session, plan = await planned(harness)
    assert session["state"] == "awaiting_user_confirmation"
    # The worker proposes; it never confirms.
    assert plan.status == "draft"
    assert plan.version == 1
    assert session["confirmed_plan_version"] is None


async def test_published_plan_exposes_ordered_steps(harness):
    created, _, plan = await planned(harness)
    response = await harness.client.get(PREFIX + f"/plans/{plan.id}")
    assert response.status_code == 200
    body = response.json()["data"]
    assert [step["ordinal"] for step in body["steps"]] == [1, 2, 3]
    assert body["assumptions"]
    first = body["steps"][0]
    assert first["status"] == "pending"
    assert first["policy_disposition"] == "allow"
    assert first["expected_result"] and first["success_criterion"]
    assert first["expected_result"] != first["success_criterion"]


async def test_plan_events_record_publication(harness):
    _, session, plan = await planned(harness)
    async with harness.app.state.sessions() as db:
        kinds = list(
            await db.scalars(
                select(m.GuidanceEvent.type)
                .where(m.GuidanceEvent.session_id == session["id"])
                .order_by(m.GuidanceEvent.sequence)
            )
        )
    assert "plan.ready" in kinds
    assert kinds.index("plan.ready") < kinds.index("plan.confirmation_required")


async def test_a_second_plan_supersedes_the_first(harness):
    created, session, first = await planned(harness)
    await request_plan(harness, created)
    await tick(harness.app)
    async with harness.app.state.sessions() as db:
        plans = list(
            await db.scalars(select(m.TaskPlan).order_by(m.TaskPlan.version))
        )
    assert [(plan.version, plan.status) for plan in plans] == [(1, "superseded"), (2, "draft")]


async def test_planning_cannot_start_while_a_plan_is_being_made(harness):
    created = await create(harness)
    await request_plan(harness, created)
    # The session is `analyzing`, which the 05 transition table does not allow a
    # plan request from, so the state gate rejects before the in-flight check.
    second = await request_plan(harness, created)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "invalid_transition"


async def test_replaying_the_same_key_does_not_queue_twice(harness):
    created = await create(harness)
    key = str(uuid4())
    version = created.json()["data"]["session"]["state_version"]
    # A replay must repeat the original body, or the key is being reused for a
    # different request and the receipt correctly refuses it.
    first = await request_plan(harness, created, key=key, expected_version=version)
    again = await request_plan(harness, created, key=key, expected_version=version)
    assert again.status_code == 202
    assert again.json()["data"]["operation_id"] == first.json()["data"]["operation_id"]
    async with harness.app.state.sessions() as db:
        assert len((await db.scalars(select(m.OperationRow))).all()) == 1


# --- confirmation ---------------------------------------------------------


async def test_confirming_binds_the_exact_version(harness):
    _, session, plan = await planned(harness)
    response = await confirm(harness, session, plan)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["plan"]["status"] == "confirmed"
    assert body["plan"]["confirmed_at"]
    assert body["session"]["confirmed_plan_version"] == plan.version
    # Confirmation is a same-state command: it still advances the version.
    assert body["session"]["state"] == "awaiting_user_confirmation"
    assert body["session"]["state_version"] > session["state_version"]


async def test_confirming_a_superseded_plan_is_rejected(harness):
    created, session, first = await planned(harness)
    await request_plan(harness, created)
    await tick(harness.app)
    current = (
        await harness.client.get(PREFIX + f"/sessions/{session['id']}")
    ).json()["data"]

    response = await confirm(harness, current, first)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_version"
    assert response.json()["error"]["details"]["current_version"] == 2


async def test_confirming_a_stale_session_version_is_rejected(harness):
    _, session, plan = await planned(harness)
    response = await confirm(harness, session, plan, expected_version=1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_version"


async def test_confirming_a_mismatched_version_number_is_rejected(harness):
    _, session, plan = await planned(harness)
    response = await confirm(harness, session, plan, plan_version=7)
    assert response.status_code == 409


async def test_another_owner_cannot_read_or_confirm_a_plan(harness):
    _, session, plan = await planned(harness)
    intruder = {"Authorization": f"Bearer {harness.token(owner=str(uuid4()))}"}
    assert (
        await harness.client.get(PREFIX + f"/plans/{plan.id}", headers=intruder)
    ).status_code in {401, 404}
    response = await harness.client.post(
        PREFIX + f"/plans/{plan.id}/confirm",
        json={"expected_version": session["state_version"], "plan_version": plan.version},
        headers={"Idempotency-Key": str(uuid4()), **intruder},
    )
    assert response.status_code in {401, 404}


# --- the planner is proposing, not deciding -------------------------------


def proposed(**overrides) -> ProposedStep:
    return ProposedStep.model_validate(
        {
            "title": "Check the version",
            "action": "Type `python --version` and press Enter.",
            "expected_result": "A version number is printed.",
            "success_criterion": "A version number is visible.",
            "fallback": "",
            "explanation": "",
            "application_key": "powershell",
        }
        | overrides
    )


def test_guard_blocks_a_restricted_step_without_dropping_it():
    disposition, risk = step_policy(proposed(action="Delete the virtual environment folder."))
    assert (disposition, risk) == ("block", "high")


def test_guard_blocks_on_a_restricted_fallback_too():
    disposition, _ = step_policy(proposed(fallback="Otherwise uninstall the package."))
    assert disposition == "block"


def test_guard_leaves_an_ordinary_step_alone():
    assert step_policy(proposed()) == ("allow", "low")


def test_descriptive_step_fields_are_not_matched():
    step = proposed(explanation="The installer will remove the old build.")
    assert step_policy(step) == ("allow", "low")


async def test_a_planner_cannot_propose_its_own_disposition():
    """policy_disposition is not in the provider schema, so a plan proposal has no
    way to claim a verdict; the caller persists what the guard returns."""
    assert "policy_disposition" not in ProposedStep.model_fields
    with pytest.raises(ValueError):
        ProposedStep.model_validate(
            {**proposed().model_dump(), "policy_disposition": "allow"}
        )


async def test_fixture_planner_is_deterministic_and_bounded():
    from app.providers.fixture import FixtureProvider

    context = PlanContext(goal="Why won't Python run?", category="debug", application_key="vscode")
    first = await FixtureProvider().plan(context)
    second = await FixtureProvider().plan(context)
    assert first == second
    assert 1 <= len(first.steps) <= 12
    assert all(step.application_key == "vscode" for step in first.steps)


def test_a_plan_cannot_exceed_twelve_steps():
    with pytest.raises(ValueError):
        ProposedPlan(steps=[proposed() for _ in range(13)])


def test_a_plan_needs_at_least_one_step():
    with pytest.raises(ValueError):
        ProposedPlan(steps=[])


def test_needs_review_message_is_shared_with_the_other_roles():
    assert NEEDS_REVIEW
