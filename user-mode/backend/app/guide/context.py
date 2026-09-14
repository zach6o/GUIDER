"""What is on the shared window, as a belief rather than a verdict.

The observer role answers one question — is this step's criterion satisfied? —
and that is enough to advance a plan and not enough to guide anyone. A guide that
knows only "not yet" cannot say the user is in the wrong application, cannot
notice a dialog blocking them, and cannot point at anything, because it never
formed an opinion about the screen at all.

This module forms that opinion, and then spends most of its effort not acting on
it. Two rules carry the design.

**A context is never evidence.** Nothing here writes `verified`, produces a
`VerificationResult`, or moves a step. `stage` is a belief the guide reads;
advancing still requires the verification path and its own bands
([ADR-019](../../../../docs/user-mode-guide/adr/019-context-engine.md)).

**An unchanged screen costs nothing.** `digest_of` hashes only the fields a guide
would act on — the application, the screen, the stage, which controls are present,
whether a dialog or an error is up. Confidence, wording and box coordinates are
deliberately excluded, because a model that describes the same screen twice in
slightly different words has not told the guide anything new. A matching digest
means the current instruction still stands and no reasoning call is made. That is
the whole economic argument for looking at every admitted frame.

Nothing here persists a frame. The `ScreenContext` row holds descriptions and a
hash; the pixels exist for one request and are gone.
"""

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.engine import record_event
from app.guide.guard import restricted_action
from app.providers.base import ContextRequest, ScreenContext

# Same window as the event stream: a context describes a moment, and a moment a
# week old explains nothing. Retention class H.
CONTEXT_RETENTION = timedelta(days=7)

# Stages that mean the guide should look again rather than act.
UNCERTAIN = frozenset({"unreadable"})

# Below this, a stage is not worth acting on at all. Matches the observer's own
# floor, because a belief and a verdict should not disagree about what "too
# unsure to matter" means.
ACT_AT = 0.60


def digest_of(context: ScreenContext) -> str:
    """A hash of what a guide would act on, and nothing else.

    Excluded on purpose: confidence, free text, and box geometry. A model that
    re-words the same screen, or nudges a box by a pixel, must not read as a
    changed screen — otherwise every frame buys a reasoning call and the design
    does not pay for itself.
    """
    parts = [
        context.application.strip().lower(),
        context.screen.strip().lower(),
        context.stage,
        "dialog" if context.dialog else "",
        "error" if context.error_text else "",
        "|".join(sorted(control.label.strip().lower() for control in context.controls)),
    ]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


def vet_context(context: ScreenContext) -> ScreenContext:
    """The guard, for this role.

    A screen is untrusted input in exactly the sense of SEC-09: text on it may
    address the model, claim to be a system prompt, or ask for something. Two
    things follow. A control whose label reads as an instruction is dropped
    rather than offered, because a mark pointing at it would be Guider acting on
    words it found on a screen. And a stage claiming the step is satisfied is
    refused when the screen could not be read at all.
    """
    safe = [
        control
        for control in context.controls
        if not restricted_action(control.label) and not _addresses_the_model(control.label)
    ]
    stage = context.stage
    if stage in {"step_satisfied", "later_step_satisfied"} and context.confidence < ACT_AT:
        # Claiming progress with no confidence behind it is the one contradiction
        # worth correcting rather than recording.
        stage = "in_progress"
    if context.error_text and _addresses_the_model(context.error_text):
        context = context.model_copy(update={"error_text": ""})
    return context.model_copy(update={"controls": safe, "stage": stage})


# Phrases that mean a line of screen text is talking to the model rather than to
# the user. Mirrors the import check in `app/imports/text.py`; kept separate
# because the surfaces differ and the lists will diverge.
_ADDRESSES = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "system:",
    "you are now",
    "new instructions",
    "act as",
)


def _addresses_the_model(text: str) -> bool:
    lowered = text.strip().lower()
    return any(phrase in lowered for phrase in _ADDRESSES)


def request_for(step: m.TaskStep, later: list[m.TaskStep]) -> ContextRequest:
    """What the observer is allowed to see: this step's testable condition, and
    the titles of steps that come after it so it can say one is already done.
    No goal, no history, no account data."""
    return ContextRequest(
        success_criterion=step.success_criterion,
        expected_result=step.expected_result,
        application_key=step.application_key,
        step_title=step.title,
        later_titles=[row.title for row in later[:11]],
    )


async def latest(db: AsyncSession, session: m.GuideSession) -> m.ScreenContextRow | None:
    return await db.scalar(
        select(m.ScreenContextRow)
        .where(
            m.ScreenContextRow.owner_id == session.owner_id,
            m.ScreenContextRow.session_id == session.id,
        )
        .order_by(m.ScreenContextRow.created_at.desc())
        .limit(1)
    )


async def save(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    context: ScreenContext,
    request_id: str,
) -> tuple[m.ScreenContextRow, bool]:
    """Record the belief and answer whether it changed anything.

    The boolean is what the caller spends money on: `False` means the screen is
    the same screen as far as the guide is concerned, and the current instruction
    still stands.
    """
    digest = digest_of(context)
    previous = await latest(db, session)
    changed = previous is None or previous.digest != digest or previous.step_id != step.id

    row = m.ScreenContextRow(
        id=m.new_id(),
        owner_id=session.owner_id,
        session_id=session.id,
        step_id=step.id,
        stage=context.stage,
        digest=digest,
        application=context.application[:80],
        application_matches_expected=context.application_matches_expected,
        screen=context.screen[:120],
        dialog=context.dialog[:200] or None,
        error_text=context.error_text[:200] or None,
        confidence=context.confidence,
        control_count=len(context.controls),
        expires_at=m.now() + CONTEXT_RETENTION,
    )
    db.add(row)
    await db.flush()
    await record_event(
        db,
        session,
        "context.changed" if changed else "context.observed",
        request_id,
        {
            "step_id": step.id,
            "stage": context.stage,
            "digest": digest,
            "confidence": round(context.confidence, 2),
            "matches_expected": context.application_matches_expected,
        },
    )
    return row, changed
