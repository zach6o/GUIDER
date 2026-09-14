"""Checking a step against a screenshot the user shared.

Until now `POST .../verifications` had one arm. The user could say a step was
done and the guide would move on, recording `user_reported` and awarding no
badge; a client that sent evidence was refused outright rather than quietly
downgraded. That refusal was honest, and it left the product's central promise —
*one verified step at a time* — half-built for anyone not being watched live.

This is the other arm. It asks the same observer role that judges a live frame,
against a still the user chose to share, and holds the answer to the same bands:

* `0.85` and above, with the criterion satisfied, is a **pass**. The step becomes
  `verified` with a timestamp and the confidence that earned it.
* `0.60` to `0.85` is **inconclusive**. Nothing advances; the user is asked, and
  their answer is recorded as their word, exactly as it is in the live path.
* Below `0.60`, or the criterion not satisfied, is a **mismatch**. The step stays
  open and the reason is saved.

The distinction that matters is the one this module exists to preserve: evidence
here is a still image the user picked, checked once. A pass means something
looked at a screen and agreed. It never means the user said so.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.engine import record_event, transition
from app.guide.observation import ADVANCE_AT, ASK_AT, VERIFICATION_RETENTION
from app.guide.steps import retire_instructions

# A still the user chose is worth a little more patience than a live frame: they
# picked the moment, so a slow answer is better than a wrong one.
VERIFY_TIMEOUT_SECONDS = 25

# How long the evidence link behind a verification stays meaningful. The image
# itself expires in 24 hours; the result of looking at it outlives it.
EVIDENCE_RETENTION = timedelta(days=30)


def outcome_for(result) -> tuple[str, bool]:
    """`(status, passed)` for one observer answer, on the bands the live path
    uses. One threshold table, two entry points."""
    if not result.step_complete:
        return "mismatch", False
    if result.confidence >= ADVANCE_AT:
        return "passed", True
    if result.confidence >= ASK_AT:
        return "inconclusive", False
    return "mismatch", False


async def evidence_for(db: AsyncSession, operation: m.OperationRow) -> list[m.ScreenshotRow]:
    return list(
        await db.scalars(
            select(m.ScreenshotRow)
            .join(m.OperationEvidence, m.OperationEvidence.screenshot_id == m.ScreenshotRow.id)
            .where(m.OperationEvidence.operation_id == operation.id)
        )
    )


async def record(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    claim: m.CompletionClaim | None,
    instruction: m.Instruction | None,
    result,
    evidence_id: str,
    request_id: str,
) -> m.VerificationResult:
    """Commit what the evidence earned, and nothing more."""
    status, passed = outcome_for(result)
    verification = m.VerificationResult(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        step_id=step.id,
        claim_id=claim.id if claim else None,
        status=status,
        verifier_kind="visual",
        reason=result.note,
        observed_confidence=result.confidence,
        # The one field that separates this from a self-report: something was
        # actually looked at.
        evidence_available=True,
        instruction_version=instruction.version if instruction else 1,
        control_epoch=session.control_epoch,
        completed_at=m.now(),
        expires_at=m.now() + VERIFICATION_RETENTION,
    )
    db.add(verification)
    if passed:
        step.status = "verified"
        step.verified_at = m.now()
        session.current_step_id = None
        session.stuck_since = None
        if instruction is not None:
            instruction.status = "superseded"
    else:
        # Not a failure of the user: the step simply is not done yet, so it stays
        # open with its instruction intact and its attempt counted.
        step.attempt_count += 1
    step.updated_at = m.now()
    await db.flush()
    await record_event(
        db,
        session,
        "verification.completed",
        request_id,
        {
            "step_id": step.id,
            "verification_id": verification.id,
            "passed": passed,
            "status": status,
            "confidence": round(result.confidence, 2),
            "evidence_id": evidence_id,
        },
    )
    return verification


async def settle(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    verification: m.VerificationResult,
    request_id: str,
) -> bool:
    """Move the session on from `verifying`, per doc 05.

    A pass goes to `active` so the next instruction is prepared. Anything else
    returns to `awaiting_user_action` with the same step still current — doc 05's
    "mismatch or inconclusive, attempts remaining" row.
    """
    if verification.status == "passed":
        await transition(db, session, "active", "step_verified", request_id)
        return True
    await transition(db, session, "awaiting_user_action", verification.status, request_id)
    return False


async def retire_if_finished(db: AsyncSession, session: m.GuideSession) -> None:
    """Leave no instruction pointing at a step that has just been verified."""
    await retire_instructions(db, session)
