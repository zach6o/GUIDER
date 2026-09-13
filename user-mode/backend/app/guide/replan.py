"""Noticing that a guide is stuck, and replacing what is left of its plan.

Two separate things live here, and the separation matters. Detection only ever
emits an event: nothing about being stuck changes session state, because a guide
that is going nowhere is still the user's to abandon or continue (doc 05).
Replacing the plan is a second, explicit act, and it produces a draft that the
user reviews like any other plan — a replan is a new roadmap, not a correction
applied behind their back (ADR-010).

Work already done is carried across untouched. A verified step stays verified,
with its `verified_at`, and points back at the row it came from through
`previous_step_id`. Nothing here can un-verify a step or re-ask for one that is
already behind the guide.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.engine import record_event
from app.guide.guard import step_policy
from app.guide.planner import PLAN_RETENTION, next_version
from app.providers.base import PlanContext, ProposedPlan

# How long one step may be the current step before the guide says so. Long
# enough that reading an instruction and doing it is never called stuck.
STUCK_AFTER = timedelta(minutes=5)

# Attempts on one step before the guide offers a different plan. The third
# attempt blocks, which is the existing cap in doc 05.
STUCK_ATTEMPTS = 2

# What an observer can report that means the plan no longer matches the screen.
PLAN_BREAKING = frozenset({"different_os", "different_app", "outdated_ui"})

# Statuses that mean a step is behind the guide rather than waiting on the user.
SETTLED = frozenset({"verified", "skipped"})


async def note_stuck(
    db: AsyncSession, session: m.GuideSession, step: m.TaskStep, why: str, request_id: str
) -> bool:
    """Say once that this task is going nowhere. No state change, by design."""
    if session.stuck_since is not None:
        return False
    session.stuck_since = m.now()
    await record_event(
        db, session, "session.stuck_detected", request_id, {"step_id": step.id, "reason": why}
    )
    return True


async def check_stuck(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    instruction: m.Instruction,
    anomaly: str,
    request_id: str,
) -> bool:
    """Three ways a guide is stuck, checked wherever evidence arrives.

    An anomaly says the plan no longer matches the screen; repeated attempts say
    the instruction is not working; elapsed time on one step says neither is
    admitting it. None of them is a failure, and none of them advances anything.
    """
    if anomaly in PLAN_BREAKING:
        return await note_stuck(db, session, step, f"anomaly:{anomaly}", request_id)
    if step.attempt_count >= STUCK_ATTEMPTS:
        return await note_stuck(db, session, step, "repeated_attempts", request_id)
    if m.now() - instruction.created_at > STUCK_AFTER:
        return await note_stuck(db, session, step, "no_progress", request_id)
    return False


async def settled_steps(db: AsyncSession, plan: m.TaskPlan) -> list[m.TaskStep]:
    """Steps a replan must not touch: verified, skipped, or already reported done
    by the user. Their order is kept, so the new plan reads as one history."""
    reported = (
        select(m.VerificationResult.step_id)
        .where(
            m.VerificationResult.owner_id == plan.owner_id,
            m.VerificationResult.status == "user_reported",
        )
        .scalar_subquery()
    )
    return list(
        await db.scalars(
            select(m.TaskStep)
            .where(
                m.TaskStep.owner_id == plan.owner_id,
                m.TaskStep.plan_id == plan.id,
                m.TaskStep.status.in_(SETTLED) | m.TaskStep.id.in_(reported),
            )
            .order_by(m.TaskStep.ordinal)
        )
    )


def context_for_replan(
    task: m.GuideTask, done: list[m.TaskStep], reason: str, anomaly: str
) -> PlanContext:
    return PlanContext(
        goal=task.goal,
        category=task.category,
        application_key=task.application_key,
        reason=reason,
        completed=[step.title for step in done][:12],
        anomaly=anomaly,
    )


async def persist_replan(
    db: AsyncSession,
    session: m.GuideSession,
    task: m.GuideTask,
    proposal: ProposedPlan,
    done: list[m.TaskStep],
) -> m.TaskPlan:
    """Write the replacement version: settled work first, then what is proposed
    for the rest. Every earlier version is superseded, never edited."""
    superseded = await db.scalars(
        select(m.TaskPlan).where(
            m.TaskPlan.owner_id == session.owner_id,
            m.TaskPlan.session_id == session.id,
            m.TaskPlan.status != "superseded",
        )
    )
    for old in superseded:
        old.status = "superseded"
        old.updated_at = m.now()

    plan = m.TaskPlan(
        id=m.new_id(),
        owner_id=session.owner_id,
        task_id=task.id,
        session_id=session.id,
        version=await next_version(db, session),
        assumptions=list(proposal.assumptions),
        expires_at=m.now() + PLAN_RETENTION,
    )
    db.add(plan)
    await db.flush()

    ordinal = 0
    for settled in done:
        ordinal += 1
        # A copy, carrying its own history: same status, same verified_at, and a
        # pointer back at the row it came from. The original is left alone.
        db.add(
            m.TaskStep(
                id=m.new_id(),
                owner_id=session.owner_id,
                plan_id=plan.id,
                session_id=session.id,
                previous_step_id=settled.id,
                ordinal=ordinal,
                title=settled.title,
                action=settled.action,
                expected_result=settled.expected_result,
                success_criterion=settled.success_criterion,
                fallback=settled.fallback,
                explanation=settled.explanation,
                application_key=settled.application_key,
                evidence_kind=settled.evidence_kind,
                required=settled.required,
                policy_disposition=settled.policy_disposition,
                risk=settled.risk,
                status=settled.status,
                attempt_count=settled.attempt_count,
                verified_at=settled.verified_at,
            )
        )

    for proposed in proposal.steps:
        ordinal += 1
        if ordinal > 12:
            break  # The plan cap is a hard limit, carried steps included.
        disposition, risk = step_policy(proposed)
        db.add(
            m.TaskStep(
                id=m.new_id(),
                owner_id=session.owner_id,
                plan_id=plan.id,
                session_id=session.id,
                ordinal=ordinal,
                title=proposed.title,
                action=proposed.action,
                expected_result=proposed.expected_result,
                success_criterion=proposed.success_criterion,
                fallback=proposed.fallback,
                explanation=proposed.explanation,
                application_key=proposed.application_key,
                evidence_kind=proposed.evidence_kind,
                required=proposed.required,
                policy_disposition=disposition,
                risk=risk,
            )
        )
    await db.flush()
    return plan


async def carried_verifications(
    db: AsyncSession, session: m.GuideSession, plan: m.TaskPlan
) -> None:
    """Copy each carried step's `user_reported` result onto the copy, so a step
    reported done stays reported done and is not handed out again."""
    copies = list(
        await db.scalars(
            select(m.TaskStep).where(
                m.TaskStep.owner_id == plan.owner_id,
                m.TaskStep.plan_id == plan.id,
                m.TaskStep.previous_step_id.is_not(None),
            )
        )
    )
    for copy in copies:
        original = await db.scalar(
            select(m.VerificationResult).where(
                m.VerificationResult.owner_id == session.owner_id,
                m.VerificationResult.step_id == copy.previous_step_id,
                m.VerificationResult.status == "user_reported",
            )
        )
        if original is None:
            continue
        db.add(
            m.VerificationResult(
                id=m.new_id(),
                owner_id=session.owner_id,
                session_id=session.id,
                step_id=copy.id,
                claim_id=original.claim_id,
                status="user_reported",
                verifier_kind="self_report",
                reason=original.reason,
                evidence_available=False,
                instruction_version=original.instruction_version,
                control_epoch=session.control_epoch,
                completed_at=original.completed_at,
                expires_at=original.expires_at,
            )
        )
    await db.flush()
