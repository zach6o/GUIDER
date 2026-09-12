from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app import models as m
from tests.conftest import ALICE, BOB
from tests.test_flow import create


async def owned_session(harness):
    """A persisted task and session to hang a plan on, plus a real second user so
    a cross-owner test fails on the composite key and not on a missing user."""
    data = (await create(harness)).json()["data"]
    async with harness.app.state.sessions() as db, db.begin():
        db.add(m.User(id=BOB))
    return data["task"]["id"], data["session"]["id"]


def plan(owner: str, task_id: str, session_id: str, **overrides) -> m.TaskPlan:
    return m.TaskPlan(
        id=m.new_id(),
        owner_id=owner,
        task_id=task_id,
        session_id=session_id,
        expires_at=m.now() + timedelta(days=30),
        **overrides,
    )


def step(owner: str, plan_row: m.TaskPlan, ordinal: int = 1, **overrides) -> m.TaskStep:
    return m.TaskStep(
        id=m.new_id(),
        owner_id=owner,
        plan_id=plan_row.id,
        session_id=plan_row.session_id,
        ordinal=ordinal,
        title="Open the terminal",
        action="Open the integrated terminal in VS Code.",
        expected_result="A terminal panel appears.",
        success_criterion="A shell prompt is visible in the lower panel.",
        fallback="Use the View menu, then Terminal.",
        explanation="The terminal is where the interpreter reports what went wrong.",
        application_key="vscode",
        **overrides,
    )


async def test_plan_and_steps_persist_with_their_defaults(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = plan(ALICE, task_id, session_id)
        db.add(row)
        await db.flush()
        db.add(step(ALICE, row))

    async with harness.app.state.sessions() as db:
        saved = await db.scalar(select(m.TaskPlan))
        first = await db.scalar(select(m.TaskStep))
    assert (saved.status, saved.version, saved.assumptions) == ("draft", 1, [])
    assert saved.policy_version == "development-1"
    assert (first.status, first.risk, first.attempt_count) == ("pending", "low", 0)
    assert (first.policy_disposition, first.evidence_kind, first.required) == (
        "allow",
        "visual",
        True,
    )
    # Shown to the user vs. tested by the verifier: deliberately separate fields.
    assert first.expected_result != first.success_criterion


async def test_deleting_a_plan_removes_its_steps(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = plan(ALICE, task_id, session_id)
        db.add(row)
        await db.flush()
        for ordinal in (1, 2, 3):
            db.add(step(ALICE, row, ordinal=ordinal))
        plan_id = row.id

    async with harness.app.state.sessions() as db, db.begin():
        await db.execute(delete(m.TaskPlan).where(m.TaskPlan.id == plan_id))

    async with harness.app.state.sessions() as db:
        assert await db.scalar(select(m.TaskPlan)) is None
        # A superseded plan version cannot leave orphan step definitions behind.
        assert (await db.scalars(select(m.TaskStep))).all() == []


async def test_a_plan_cannot_reference_another_owners_session(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db:
        db.add(plan(BOB, task_id, session_id))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_a_step_cannot_reference_another_owners_plan(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = plan(ALICE, task_id, session_id)
        db.add(row)

    async with harness.app.state.sessions() as db:
        db.add(step(BOB, row))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_one_version_number_per_session(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        db.add(plan(ALICE, task_id, session_id, version=2))

    async with harness.app.state.sessions() as db:
        db.add(plan(ALICE, task_id, session_id, version=2))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_one_step_per_ordinal_within_a_plan(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = plan(ALICE, task_id, session_id)
        db.add(row)
        await db.flush()
        db.add(step(ALICE, row, ordinal=4))

    async with harness.app.state.sessions() as db:
        db.add(step(ALICE, row, ordinal=4))
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.parametrize("ordinal", [0, 13])
async def test_plans_stay_within_twelve_steps(harness, ordinal):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = plan(ALICE, task_id, session_id)
        db.add(row)

    async with harness.app.state.sessions() as db:
        db.add(step(ALICE, row, ordinal=ordinal))
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("status", "approved"),
        ("risk", "critical"),
        ("policy_disposition", "maybe"),
        ("evidence_kind", "vibes"),
    ],
)
async def test_step_enums_are_enforced_by_the_database(harness, column, value):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = plan(ALICE, task_id, session_id)
        db.add(row)

    async with harness.app.state.sessions() as db:
        db.add(step(ALICE, row, **{column: value}))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_plan_status_is_enforced_by_the_database(harness):
    task_id, session_id = await owned_session(harness)
    async with harness.app.state.sessions() as db:
        db.add(plan(ALICE, task_id, session_id, status="approved"))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_unknown_session_is_rejected_even_for_the_right_owner(harness):
    task_id, _ = await owned_session(harness)
    async with harness.app.state.sessions() as db:
        db.add(plan(ALICE, task_id, str(uuid4())))
        with pytest.raises(IntegrityError):
            await db.commit()
