"""Step progression. Like session state, only the engine writes it.

A claim is the user's word and a verification is evidence. They are separate
records and separate statuses here, because collapsing them is exactly the
mistake ADR-010 exists to prevent: `user_claimed` is not `verified`, and nothing
in this module can turn one into the other.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.errors import GuideError, not_found
from app.guide.engine import record_event

INSTRUCTION_RETENTION = timedelta(days=30)
# A step that still needs the user to do something.
OPEN_STATUSES = frozenset({"pending", "instruction_ready", "awaiting_user_action", "user_claimed"})


async def confirmed_plan(db: AsyncSession, session: m.GuideSession) -> m.TaskPlan:
    plan = await db.scalar(
        select(m.TaskPlan).where(
            m.TaskPlan.owner_id == session.owner_id,
            m.TaskPlan.session_id == session.id,
            m.TaskPlan.status == "confirmed",
        )
    )
    if plan is None or plan.version != session.confirmed_plan_version:
        raise GuideError(409, "invalid_transition", "Confirm a plan before starting.")
    return plan


async def next_open_step(db: AsyncSession, plan: m.TaskPlan) -> m.TaskStep | None:
    """The lowest-ordinal step still waiting on the user. Blocked steps are not
    handed out: a blocked step cannot produce an instruction (ADR-012)."""
    return await db.scalar(
        select(m.TaskStep)
        .where(
            m.TaskStep.owner_id == plan.owner_id,
            m.TaskStep.plan_id == plan.id,
            m.TaskStep.status.in_(OPEN_STATUSES),
            m.TaskStep.policy_disposition != "block",
        )
        .order_by(m.TaskStep.ordinal)
        .limit(1)
    )


async def owned_step(db: AsyncSession, session: m.GuideSession, step_id: str) -> m.TaskStep:
    step = await db.scalar(
        select(m.TaskStep).where(
            m.TaskStep.id == step_id,
            m.TaskStep.owner_id == session.owner_id,
            m.TaskStep.session_id == session.id,
        )
    )
    if step is None:
        raise not_found()
    return step


async def current_instruction(
    db: AsyncSession, session: m.GuideSession
) -> m.Instruction | None:
    return await db.scalar(
        select(m.Instruction).where(
            m.Instruction.owner_id == session.owner_id,
            m.Instruction.session_id == session.id,
            m.Instruction.status == "ready",
        )
    )


async def publish_instruction(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    proposal,
    request_id: str,
) -> m.Instruction:
    """Supersede the previous instruction and make this one current."""
    previous = await db.scalars(
        select(m.Instruction).where(
            m.Instruction.owner_id == session.owner_id,
            m.Instruction.session_id == session.id,
            m.Instruction.status == "ready",
        )
    )
    for old in previous:
        old.status = "superseded"
        old.updated_at = m.now()

    version = (
        await db.scalar(
            select(m.Instruction.version)
            .where(
                m.Instruction.owner_id == session.owner_id,
                m.Instruction.step_id == step.id,
            )
            .order_by(m.Instruction.version.desc())
            .limit(1)
        )
        or 0
    ) + 1
    instruction = m.Instruction(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        step_id=step.id,
        version=version,
        what=proposal.what,
        where=proposal.where,
        why=proposal.why or None,
        confirmation_hint=proposal.confirmation_hint,
        cannot_find_hint=proposal.cannot_find_hint,
        control_epoch=session.control_epoch,
        expires_at=m.now() + INSTRUCTION_RETENTION,
    )
    db.add(instruction)
    step.status = "instruction_ready"
    step.updated_at = m.now()
    session.current_step_id = step.id
    await db.flush()
    await record_event(
        db,
        session,
        "instruction.ready",
        request_id,
        {"instruction_id": instruction.id, "step_id": step.id, "version": version},
    )
    return instruction


async def record_claim(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    statement: str,
    request_id: str,
) -> m.CompletionClaim:
    """Record that the user says a step is done.

    This does not verify anything. The step becomes `user_claimed`, never
    `verified`; only evidence can do that, and evidence arrives with observation.
    """
    instruction = await current_instruction(db, session)
    if instruction is None or instruction.step_id != step.id:
        raise GuideError(409, "invalid_transition", "There is no current instruction to confirm.")
    superseded = await db.scalars(
        select(m.CompletionClaim).where(
            m.CompletionClaim.owner_id == session.owner_id,
            m.CompletionClaim.step_id == step.id,
            m.CompletionClaim.status == "user_claimed",
        )
    )
    for old in superseded:
        old.status = "superseded"
        old.updated_at = m.now()

    claim = m.CompletionClaim(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        step_id=step.id,
        statement=statement,
        instruction_version=instruction.version,
    )
    db.add(claim)
    step.status = "user_claimed"
    step.attempt_count += 1
    step.updated_at = m.now()
    await db.flush()
    await record_event(
        db,
        session,
        "step.user_claimed",
        request_id,
        {"step_id": step.id, "claim_id": claim.id, "verified": False},
    )
    return claim


async def skip_step(
    db: AsyncSession, session: m.GuideSession, step: m.TaskStep, request_id: str
) -> None:
    step.status = "skipped"
    step.updated_at = m.now()
    await db.flush()
    await record_event(db, session, "step.skipped", request_id, {"step_id": step.id})
