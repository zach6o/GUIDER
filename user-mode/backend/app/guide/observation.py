"""Tier 2: what happens to one admitted frame.

The browser already discarded almost everything (ADR-016 tiers 0 and 1). What
arrives here has settled, cleared the local rate limit, and belongs to a step the
user is actually working on. This module spends the budget, asks the observer,
and decides what the verdict is worth.

The frame itself is never persisted. It exists in memory for one request; only
the outcome becomes an event.
"""

import asyncio
from datetime import timedelta

from app import models as m
from app.errors import GuideError
from app.guide.engine import record_event, transition

# Per-session ceilings from ADR-016. Enforced again here because the browser's
# limiter is advice: it runs on the user's machine and can be bypassed.
MAX_OBSERVATION_CALLS = 200
MAX_FRAMES_PER_MINUTE = 12
MAX_OBSERVATION_MINUTES = 30

# Confidence bands. Advancing on weak evidence is the product's worst failure,
# so the middle band asks instead of guessing, and the bottom band stays quiet.
ADVANCE_AT = 0.85
ASK_AT = 0.60

VERIFICATION_RETENTION = timedelta(days=30)

# The notice the user agreed to. Draft until D06 approves the wording; a session
# that accepted an older version must be asked again rather than silently carried
# forward, which is what pinning the version here buys.
NOTICE_VERSION = "observation-draft-1"


def calls_remaining(session: m.GuideSession) -> int:
    return max(0, MAX_OBSERVATION_CALLS - session.observation_calls)


async def enable(db, session: m.GuideSession, consent_version: str, request_id: str) -> None:
    """Switch watching on. Off is the default and every path back to off is
    cheaper than this one (ADR-003, preserved by ADR-016)."""
    if consent_version != NOTICE_VERSION:
        raise GuideError(
            409,
            "consent_version_mismatch",
            "The notice about watching has changed. Read it again before switching this on.",
            details={"current_version": None},
        )
    session.observation_active = True
    session.observation_mode = "window"
    session.observation_started_at = m.now()
    session.last_user_activity_at = m.now()
    await record_event(
        db,
        session,
        "observation.enabled",
        request_id,
        {"consent_version": consent_version, "budget": MAX_OBSERVATION_CALLS},
    )


async def stop(db, session: m.GuideSession, reason: str, request_id: str) -> None:
    """One tap, and everything in flight stops counting.

    Incrementing control_epoch is what makes this immediate rather than advisory:
    work bound to the old epoch is discarded wherever it is, exactly as pause and
    stop already do.
    """
    session.observation_active = False
    session.observation_mode = "screenshot_only"
    session.observation_started_at = None
    session.control_epoch += 1
    session.last_user_activity_at = m.now()
    await record_event(
        db,
        session,
        "observation.stopped",
        request_id,
        {"reason": reason, "frames_observed": session.frames_observed},
    )


class SessionGate:
    """One observation in flight per session, and a per-minute window.

    In-process: a single local worker and API, matching the rest of this slice.
    A distributed limiter is listed in doc 20's remaining work.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._recent: dict[str, list[float]] = {}

    def lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def admit(self, session_id: str, now: float) -> None:
        recent = [at for at in self._recent.get(session_id, []) if at > now - 60]
        if len(recent) >= MAX_FRAMES_PER_MINUTE:
            raise GuideError(
                429,
                "rate_limited",
                "Guider is looking too often. It will catch up in a moment.",
                retryable=True,
            )
        recent.append(now)
        self._recent[session_id] = recent

    def forget(self, session_id: str) -> None:
        self._locks.pop(session_id, None)
        self._recent.pop(session_id, None)


def check_budget(session: m.GuideSession) -> None:
    """Budget exhaustion is a supported mode, not an error: guidance continues
    with user-driven checking. The message says so."""
    if session.observation_calls >= MAX_OBSERVATION_CALLS:
        raise GuideError(
            429,
            "observation_budget_spent",
            "Guider has watched as much as this session allows. "
            "Keep going and tell it when a step is done.",
        )
    started = session.observation_started_at
    if started and m.now() - started > timedelta(minutes=MAX_OBSERVATION_MINUTES):
        raise GuideError(
            429,
            "observation_budget_spent",
            "Watching has been on for a while. "
            "Keep going and tell it when a step is done.",
        )


def band(result) -> str:
    """`advance`, `ask` or `wait`. Evidence decides; elapsed time never does."""
    if not result.step_complete:
        return "wait"
    if result.confidence >= ADVANCE_AT:
        return "advance"
    return "ask" if result.confidence >= ASK_AT else "wait"


async def apply(
    db,
    session: m.GuideSession,
    step: m.TaskStep,
    instruction: m.Instruction,
    result,
    request_id: str,
) -> str:
    """Commit what the verdict earns. Only `advance` moves the session."""
    session.observation_calls += 1
    session.frames_observed += 1
    decision = band(result)

    await record_event(
        db,
        session,
        "observation.tick",
        request_id,
        {
            "step_id": step.id,
            "decision": decision,
            "confidence": round(result.confidence, 2),
            "ui_changed": result.ui_changed,
            "anomaly": result.anomaly,
        },
    )
    if decision != "advance":
        return decision

    # awaiting_user_action -> verifying on accepted new evidence, per doc 05.
    await transition(db, session, "verifying", "observed_evidence", request_id)
    verification = m.VerificationResult(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        step_id=step.id,
        status="passed",
        verifier_kind="visual",
        reason=result.note,
        observed_confidence=result.confidence,
        instruction_version=instruction.version,
        control_epoch=session.control_epoch,
        completed_at=m.now(),
        expires_at=m.now() + VERIFICATION_RETENTION,
    )
    db.add(verification)
    step.status = "verified"
    step.verified_at = m.now()
    step.updated_at = m.now()
    instruction.status = "superseded"
    session.current_step_id = None
    session.stuck_since = None
    await db.flush()
    await record_event(
        db,
        session,
        "verification.completed",
        request_id,
        {"step_id": step.id, "verification_id": verification.id, "passed": True},
    )
    # verifying -> active: the step advanced, so the next instruction is prepared.
    await transition(db, session, "active", "step_verified", request_id)
    return decision
