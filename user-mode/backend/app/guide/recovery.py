"""Getting a paused or blocked session moving again.

Every route that stops a guide existed before this module: pause, the safety
guard's block, a failed instruction, and — since the feedback route — the user
saying the guidance was wrong. Nothing brought one back. A session could be
stopped in four ways and resumed in none, which made `blocked` a polite word for
abandoned.

Doc 05 says what coming back means, and the two halves are separate on purpose.
Resuming returns the session to a stable checkpoint after the user has reviewed
where it is; it restores no screen permission, because a grant belongs to the
session that was interrupted. Retrying asks for the current step to be explained
again, and changes nothing about the step's status — a step is still done only
when evidence or the user says so.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.errors import GuideError
from app.guide.engine import CHECKPOINTS, TERMINAL, record_event, transition
from app.guide.steps import confirmed_plan

# Attempts on one step before a retry is refused. The third attempt is where
# doc 05 stops offering revisions and the guide should be asking for a different
# plan instead, which is what `POST /sessions/{id}/replan` is for.
MAX_ATTEMPTS = 3

RESUMABLE = frozenset({"paused", "blocked"})


async def has_confirmed_plan(db: AsyncSession, session: m.GuideSession) -> bool:
    try:
        await confirmed_plan(db, session)
    except GuideError:
        return False
    return True


async def checkpoint_for(db: AsyncSession, session: m.GuideSession) -> str:
    """Where this session should come back to.

    The recorded checkpoint is trusted when it is one, because it is the state
    the session was actually in. Anything else is rebuilt from what exists: a
    confirmed plan means there is a step to stand on, and without one the user is
    back at reviewing the roadmap rather than being pointed at their screen.
    """
    recorded = session.checkpoint_state
    if recorded in CHECKPOINTS:
        return recorded
    if await has_confirmed_plan(db, session):
        return "awaiting_user_action"
    return "awaiting_user_confirmation"


async def resume(
    db: AsyncSession,
    session: m.GuideSession,
    mode: str,
    checkpoint_reviewed: bool,
    request_id: str,
) -> str:
    """Return the session to its checkpoint. Answers the state it resumed to."""
    if session.state in TERMINAL:
        raise GuideError(410, "session_ended", "This task has already finished.")
    if session.state not in RESUMABLE:
        raise GuideError(409, "invalid_transition", "This task is not waiting to be resumed.")
    if not checkpoint_reviewed:
        # Doc 05: the context is reviewed before the guide points again. A guide
        # that resumed straight into an instruction after being told it was wrong
        # would be repeating the thing the user objected to.
        raise GuideError(
            409,
            "context_review_required",
            "Look over where the task got to before picking it up again.",
        )

    target = await checkpoint_for(db, session)
    if target == "awaiting_user_action" and not await has_confirmed_plan(db, session):
        raise GuideError(409, "plan_unconfirmed", "Confirm a plan before continuing this task.")

    if mode == "window":
        # No grant is restored, ever. Choosing to be watched again is a fresh
        # decision with its own notice, so the session waits for one.
        target = "awaiting_screen_permission"

    session.observation_active = False
    session.observation_mode = "screenshot_only"
    session.observation_started_at = None
    # Whatever the guide was stuck on belonged to the run that was interrupted.
    session.stuck_since = None
    session.last_user_activity_at = m.now()
    await transition(db, session, target, "resumed", request_id)
    await record_event(
        db,
        session,
        "session.resumed",
        request_id,
        {"checkpoint": target, "mode": mode},
    )
    return target


async def current_open_step(db: AsyncSession, session: m.GuideSession) -> m.TaskStep | None:
    """The step the session is on, as the session itself records it."""
    if session.current_step_id is None:
        return None
    return await db.scalar(
        select(m.TaskStep).where(
            m.TaskStep.owner_id == session.owner_id,
            m.TaskStep.id == session.current_step_id,
        )
    )


def check_retryable(step: m.TaskStep) -> None:
    """Doc 07's two refusals, in the order that matters.

    A blocked step is refused first: no number of attempts makes a step Guider
    will not explain into one it will (ADR-012).
    """
    if step.policy_disposition == "block":
        raise GuideError(
            409,
            "blocked_task",
            "Guider will not walk you through this step. It needs separate review.",
        )
    if step.attempt_count >= MAX_ATTEMPTS:
        raise GuideError(
            409,
            "retry_limit",
            "Saying this a different way is not working. Ask for a different plan instead.",
        )


async def record_retry(
    db: AsyncSession, session: m.GuideSession, step: m.TaskStep, reason: str, request_id: str
) -> None:
    """One more attempt on this step, counted.

    Counting matters beyond the limit: `attempt_count` is what the stuck detector
    reads, so asking twice for the same step to be reworded is one of the ways a
    guide says it is going nowhere.
    """
    step.attempt_count += 1
    step.updated_at = m.now()
    await db.flush()
    await record_event(
        db,
        session,
        "step.retry_requested",
        request_id,
        {"step_id": step.id, "attempt": step.attempt_count, "reason": reason[:200]},
    )
