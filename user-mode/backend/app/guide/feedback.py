"""What the user says about guidance they were given.

Three of the four kinds are opinions and change nothing. `incorrect_guidance` is
different: doc 05 makes it invalidate the pointer, cancel the verification
attempt, revoke observation and block the session, because guidance the user has
just called wrong must not keep pointing at their screen.

It is also the only ground truth this product ever gets about a verdict the
observer reached by itself. Frames are never persisted, so when the user says an
auto-verified step was not done, this row and the `observation.tick` event that
preceded it are the entire record that the 0.85 band advanced too early. D05
calibration reads exactly that pairing, which is why the contradicted
verification's id and confidence are copied onto the row rather than looked up
later: the verification expires, the finding should not.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide import observation
from app.guide.engine import record_event, transition

FEEDBACK_RETENTION = timedelta(days=30)

# Kinds that change nothing. Saying guidance was helpful is not an event the
# session needs to survive.
OPINIONS = frozenset({"helpful", "unhelpful", "privacy_concern"})


async def latest_verification(
    db: AsyncSession, session: m.GuideSession, step_id: str
) -> m.VerificationResult | None:
    return await db.scalar(
        select(m.VerificationResult)
        .where(
            m.VerificationResult.owner_id == session.owner_id,
            m.VerificationResult.session_id == session.id,
            m.VerificationResult.step_id == step_id,
        )
        .order_by(m.VerificationResult.created_at.desc())
        .limit(1)
    )


async def contradict(
    db: AsyncSession, session: m.GuideSession, step: m.TaskStep, request_id: str
) -> m.VerificationResult | None:
    """Undo a pass the user says did not happen.

    A `passed` result becomes a `mismatch` and the step goes back to `pending`:
    the work still needs doing, and leaving a verified badge on it would be the
    false pass ADR-010 exists to prevent. A `user_reported` result is left alone
    — the user is contradicting Guider here, not themselves.
    """
    verification = await latest_verification(db, session, step.id)
    if verification is None or verification.status != "passed":
        return None
    verification.status = "mismatch"
    verification.reason = (verification.reason + " Contradicted by the user.").strip()
    step.status = "pending"
    step.verified_at = None
    step.updated_at = m.now()
    await db.flush()
    await record_event(
        db,
        session,
        "verification.contradicted",
        request_id,
        {
            "step_id": step.id,
            "verification_id": verification.id,
            "verifier_kind": verification.verifier_kind,
            "confidence": verification.observed_confidence,
        },
    )
    return verification


async def cancel_verifications(db: AsyncSession, session: m.GuideSession) -> None:
    """Doc 05: the current verification attempt does not survive being called
    wrong. Anything still pending is abandoned rather than allowed to land."""
    for pending in await db.scalars(
        select(m.VerificationResult).where(
            m.VerificationResult.owner_id == session.owner_id,
            m.VerificationResult.session_id == session.id,
            m.VerificationResult.status == "pending",
        )
    ):
        pending.status = "canceled"
    await db.flush()


async def invalidate_instructions(db: AsyncSession, session: m.GuideSession) -> None:
    """Remove the pointer. `invalidated`, not `superseded`: nothing replaced this
    instruction, it was withdrawn."""
    for ready in await db.scalars(
        select(m.Instruction).where(
            m.Instruction.owner_id == session.owner_id,
            m.Instruction.session_id == session.id,
            m.Instruction.status == "ready",
        )
    ):
        ready.status = "invalidated"
        ready.updated_at = m.now()
    await db.flush()


async def record(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep | None,
    kind: str,
    text: str,
    instruction_id: str | None,
    request_id: str,
) -> m.UserFeedback:
    """Save the feedback and, for `incorrect_guidance`, act on it."""
    contradicted = None
    if kind == "incorrect_guidance" and step is not None:
        contradicted = await contradict(db, session, step, request_id)

    feedback = m.UserFeedback(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        step_id=step.id if step else None,
        instruction_id=instruction_id,
        kind=kind,
        text=text,
        verification_id=contradicted.id if contradicted else None,
        observed_confidence=contradicted.observed_confidence if contradicted else None,
        control_epoch=session.control_epoch,
        expires_at=m.now() + FEEDBACK_RETENTION,
    )
    db.add(feedback)
    await db.flush()
    await record_event(
        db,
        session,
        "feedback.recorded",
        request_id,
        {
            "feedback_id": feedback.id,
            "kind": kind,
            "step_id": step.id if step else None,
            # The number the calibration report is built from. Null unless the
            # user contradicted something the observer decided on its own.
            "contradicted_confidence": feedback.observed_confidence,
        },
    )
    if kind in OPINIONS:
        return feedback

    # Everything below is doc 05's incorrect_guidance row, in its order.
    await invalidate_instructions(db, session)
    await cancel_verifications(db, session)
    if session.observation_active:
        await observation.stop(db, session, "incorrect_guidance", request_id)
    else:
        session.control_epoch += 1
    if session.state not in {"paused", "blocked", "analyzing"}:
        session.checkpoint_state = session.state
    session.current_step_id = None
    session.last_user_activity_at = m.now()
    await transition(db, session, "blocked", "incorrect_guidance", request_id)
    return feedback
