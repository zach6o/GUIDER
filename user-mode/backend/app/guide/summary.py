"""Writing down what actually happened.

The rule the rest of the system spends its effort maintaining — a claim is not a
verification — is easiest to lose at the end, in a sentence that says "all done".
So the summary is built deterministically from the records rather than written by
a model, and it keeps the two apart in its shape: verified steps and unverified
steps are separate lists, and the prose says which is which
([02](../../../../docs/user-mode-guide/02-functional-specification.md) F09/F12,
ADR-010).

`achieved` therefore means something specific: every required step was checked by
evidence. A session where the user reported the work themselves ends
`user_reported`, however confident they were.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.errors import GuideError
from app.guide.engine import record_event

SUMMARY_RETENTION = timedelta(days=30)

# Steps that are behind the guide with evidence, and without it.
VERIFIED = "verified"
SELF_REPORTED = "user_reported"


async def plan_for(db: AsyncSession, session: m.GuideSession) -> m.TaskPlan | None:
    return await db.scalar(
        select(m.TaskPlan).where(
            m.TaskPlan.owner_id == session.owner_id,
            m.TaskPlan.session_id == session.id,
            m.TaskPlan.status == "confirmed",
        )
    )


async def steps_and_reports(
    db: AsyncSession, session: m.GuideSession, plan: m.TaskPlan
) -> tuple[list[m.TaskStep], set[str]]:
    steps = list(
        await db.scalars(
            select(m.TaskStep)
            .where(
                m.TaskStep.owner_id == plan.owner_id,
                m.TaskStep.plan_id == plan.id,
            )
            .order_by(m.TaskStep.ordinal)
        )
    )
    reported = set(
        await db.scalars(
            select(m.VerificationResult.step_id).where(
                m.VerificationResult.owner_id == session.owner_id,
                m.VerificationResult.status == SELF_REPORTED,
            )
        )
    )
    return steps, reported


def sentences(
    verified: list[m.TaskStep],
    reported: list[m.TaskStep],
    skipped: list[m.TaskStep],
    blocked: list[m.TaskStep],
    outstanding: list[m.TaskStep],
    outcome: str,
) -> str:
    """Plain counts, in the order a person would ask for them.

    No adjectives, and no claim of success the records do not carry: this text is
    read by someone deciding whether they are finished.
    """
    total = len(verified) + len(reported) + len(skipped) + len(blocked) + len(outstanding)
    parts = [f"{total} step{'' if total == 1 else 's'} in this plan."]
    if verified:
        parts.append(
            f"{len(verified)} {'was' if len(verified) == 1 else 'were'} checked on screen."
        )
    if reported:
        parts.append(
            f"{len(reported)} you told Guider {'was' if len(reported) == 1 else 'were'} done; "
            "nothing checked those."
        )
    if skipped:
        parts.append(f"{len(skipped)} {'was' if len(skipped) == 1 else 'were'} skipped.")
    if blocked:
        parts.append(
            f"{len(blocked)} need{'s' if len(blocked) == 1 else ''} separate review and "
            "Guider did not walk you through "
            f"{'it' if len(blocked) == 1 else 'them'}."
        )
    if outstanding:
        parts.append(
            f"{len(outstanding)} {'was' if len(outstanding) == 1 else 'were'} never started."
        )
    if outcome == "achieved":
        parts.append("Every required step was checked.")
    elif outcome == SELF_REPORTED:
        parts.append("This is your own account of the work, not a check of it.")
    elif outcome == "stopped":
        parts.append("You stopped this task.")
    return " ".join(parts)[:4000]


def corrections_for(
    skipped: list[m.TaskStep], blocked: list[m.TaskStep], outstanding: list[m.TaskStep]
) -> list[str]:
    """What a reader would want flagged, named by step rather than counted."""
    notes = [f"Step {step.ordinal} was skipped: {step.title}" for step in skipped]
    notes += [f"Step {step.ordinal} needs separate review: {step.title}" for step in blocked]
    notes += [f"Step {step.ordinal} was never started: {step.title}" for step in outstanding]
    return notes[:12]


def unverified_ready(steps: list[m.TaskStep], reported: set[str]) -> bool:
    """Whether `user_reported` completion is honest: every required step is either
    behind the guide or explicitly skipped. A blocked required step is not."""
    for step in steps:
        if not step.required:
            continue
        if step.policy_disposition == "block":
            return False
        if step.status in {VERIFIED, "skipped"} or step.id in reported:
            continue
        return False
    return True


def verified_ready(steps: list[m.TaskStep]) -> bool:
    """Whether `achieved` is true: evidence for every required step. The user's
    own word does not count here, which is the entire point of the outcome."""
    return all(
        step.status == VERIFIED for step in steps if step.required
    ) and bool(steps)


async def write_summary(
    db: AsyncSession,
    session: m.GuideSession,
    outcome: str,
    request_id: str,
    self_report: str = "",
) -> m.SessionSummary:
    """Build the session's summary from its records and store it once.

    Called on completion and on stop, so a finished task always has one to show
    in history ([02](../../../../docs/user-mode-guide/02-functional-specification.md) F12).
    """
    existing = await db.scalar(
        select(m.SessionSummary).where(
            m.SessionSummary.owner_id == session.owner_id,
            m.SessionSummary.session_id == session.id,
        )
    )
    if existing is not None:
        return existing

    plan = await plan_for(db, session)
    steps: list[m.TaskStep] = []
    reported: set[str] = set()
    if plan is not None:
        steps, reported = await steps_and_reports(db, session, plan)

    verified = [step for step in steps if step.status == VERIFIED]
    self_reported = [step for step in steps if step.status != VERIFIED and step.id in reported]
    skipped = [step for step in steps if step.status == "skipped"]
    blocked = [step for step in steps if step.policy_disposition == "block"]
    settled = {step.id for step in verified + self_reported + skipped + blocked}
    outstanding = [step for step in steps if step.id not in settled]

    summary = m.SessionSummary(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        outcome=outcome,
        verified_steps=[step.id for step in verified],
        # Everything a reader must not mistake for checked work, in one list.
        unverified_steps=[step.id for step in self_reported + skipped + outstanding],
        corrections=corrections_for(skipped, blocked, outstanding),
        text=sentences(verified, self_reported, skipped, blocked, outstanding, outcome),
        next_action=(
            f"Step {blocked[0].ordinal} still needs separate review."
            if blocked
            else None
        ),
        expires_at=m.now() + SUMMARY_RETENTION,
    )
    if self_report.strip():
        summary.corrections = [*summary.corrections, f"You said: {self_report.strip()[:500]}"][:13]
    db.add(summary)
    await db.flush()
    await record_event(
        db,
        session,
        "session.completed",
        request_id,
        {
            "outcome": outcome,
            "verified": len(verified),
            "self_reported": len(self_reported),
            "skipped": len(skipped),
        },
    )
    return summary


async def require_ending(
    db: AsyncSession, session: m.GuideSession, outcome: str
) -> None:
    """Refuse an ending the records do not support.

    `achieved` needs evidence for every required step; `user_reported` needs every
    required step dealt with and none of them blocked. Neither can be asserted
    into existence by the client asking for it.
    """
    plan = await plan_for(db, session)
    if plan is None:
        raise GuideError(409, "invalid_transition", "There is no confirmed plan to finish.")
    steps, reported = await steps_and_reports(db, session, plan)
    if outcome == "achieved" and not verified_ready(steps):
        raise GuideError(
            409,
            "verification_required",
            "Some steps have not been checked. "
            "Finish as your own account instead, or check the rest first.",
        )
    if outcome == SELF_REPORTED and not unverified_ready(steps, reported):
        raise GuideError(
            409,
            "verification_required",
            "Some steps are still open, or need separate review. "
            "Skip what you are not doing first.",
        )
