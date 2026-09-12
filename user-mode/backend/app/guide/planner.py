"""Role `plan`: turn a confirmed goal into a persisted, unconfirmed roadmap.

The planner proposes; it never confirms. Every step is persisted with the guard's
verdict, not the provider's, and a new version supersedes the previous one rather
than editing it — plan definitions are immutable once written
([05](../../../../docs/user-mode-guide/05-session-state-machine.md), ADR-010).
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.guard import step_policy
from app.providers.base import PlanContext, ProposedPlan

PLAN_RETENTION = timedelta(days=30)


async def next_version(db: AsyncSession, session: m.GuideSession) -> int:
    current = await db.scalar(
        select(m.TaskPlan.version)
        .where(
            m.TaskPlan.owner_id == session.owner_id,
            m.TaskPlan.session_id == session.id,
        )
        .order_by(m.TaskPlan.version.desc())
        .limit(1)
    )
    return (current or 0) + 1


def context_for(task: m.GuideTask) -> PlanContext:
    return PlanContext(
        goal=task.goal, category=task.category, application_key=task.application_key
    )


async def persist(
    db: AsyncSession,
    session: m.GuideSession,
    task: m.GuideTask,
    proposal: ProposedPlan,
) -> m.TaskPlan:
    """Write a new draft version and supersede every earlier one."""
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

    for ordinal, proposed in enumerate(proposal.steps, start=1):
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
                # The guard's verdict, never the provider's proposal.
                policy_disposition=disposition,
                risk=risk,
            )
        )
    await db.flush()
    return plan


async def steps_for(db: AsyncSession, plan: m.TaskPlan) -> list[m.TaskStep]:
    return list(
        await db.scalars(
            select(m.TaskStep)
            .where(
                m.TaskStep.owner_id == plan.owner_id,
                m.TaskStep.plan_id == plan.id,
            )
            .order_by(m.TaskStep.ordinal)
        )
    )
