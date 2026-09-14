"""Choosing what to say next, from what is actually on the screen.

`next_open_step` hands out the lowest-numbered step still waiting. That is a
correct plan reader and a poor instructor: it cannot tell that the user already
did step four, that they are in the wrong application, that a dialog is blocking
them, or that they wandered off and need bringing back. This module reads the
belief the Context Engine formed and decides which of those is happening.

Three rules bound it, and they are the difference between adapting and
improvising.

**Nothing outside the confirmed plan.** The selector may point at a different
step of the version the user confirmed. It may never invent one. A step that is
not in that version needs a new plan and a new confirmation
([ADR-010](../../../../docs/user-mode-guide/adr/010-one-step-guidance.md)).

**Nothing is marked done here.** `step_satisfied` hands the step to the
verification path, which decides on its own bands whether the confidence earns
`verified`. A selector that could settle a step would be a second, quieter way to
pass one.

**Skipping forward asks.** It is the only adaptive move that changes the user's
record rather than the words on screen, so it names every step it would skip and
waits for one tap. Everything else is a change of wording.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.context import ACT_AT
from app.guide.engine import record_event
from app.guide.replan import note_stuck

# Consecutive contexts on one step that say the user is somewhere else before the
# guide treats it as going nowhere. Two is a moment of confusion; three is a
# pattern, and the same threshold repeated claims already use.
OFF_TRACK_LIMIT = 3


@dataclass(frozen=True)
class Decision:
    """What the guide should do about this screen.

    `reinstruct` is the only field that costs money: it is what asks for the
    instruction role to run again.
    """

    action: str
    reinstruct: bool = False
    #: For `offer_skip`, the steps a forward skip would settle, in order.
    skippable: tuple[str, ...] = ()
    #: Copy for the island, in the user's language. Empty when nothing is wrong.
    message: str = ""


def message_for(action: str, context, step_title: str) -> str:
    if action == "wrong_application":
        seen = context.application.strip() or "something else"
        return f"That looks like {seen}. Go back to where the step is happening."
    if action == "redirect":
        return "This does not look like the right screen for this step yet."
    if action == "dialog":
        text = (context.dialog or "").strip()
        return f"Deal with this first: {text}" if text else "A dialog is waiting for you."
    if action == "offer_skip":
        return "This looks further along than the plan. Shall I move ahead?"
    if action == "unreadable":
        return "Guider cannot read this window clearly."
    return ""


def decide(context, step: m.TaskStep, later: list[m.TaskStep]) -> Decision:
    """One belief, one decision. Pure, so the table below is the whole rule."""
    stage = context.stage

    if stage == "unreadable":
        # Not an error and not evidence of anything. The guide keeps working on
        # the user's word, and says once that it cannot see.
        return Decision("unreadable", message=message_for("unreadable", context, step.title))

    if stage == "blocked_dialog":
        return Decision(
            "dialog", reinstruct=True, message=message_for("dialog", context, step.title)
        )

    if stage == "off_track" or not context.application_matches_expected:
        action = "wrong_application" if not context.application_matches_expected else "redirect"
        return Decision(action, reinstruct=True, message=message_for(action, context, step.title))

    if stage == "later_step_satisfied" and context.confidence >= ACT_AT:
        index = context.satisfied_later_index
        if index is not None and 0 <= index < len(later):
            # Everything up to and including the step the screen satisfies. The
            # user sees all of them named before anything happens.
            return Decision(
                "offer_skip",
                skippable=tuple(row.id for row in later[: index + 1]),
                message=message_for("offer_skip", context, step.title),
            )
        return Decision("none")

    if stage == "step_satisfied":
        # Handed to verification, which is the only thing that can pass a step.
        return Decision("check")

    return Decision("none")


async def apply(
    db: AsyncSession,
    session: m.GuideSession,
    step: m.TaskStep,
    instruction: m.Instruction | None,
    decision: Decision,
    request_id: str,
) -> None:
    """Record what the decision was, and count the ones that mean trouble.

    No state is written here. The engine remains the only writer; this appends
    events and, when the same step keeps going wrong, says so once through the
    stuck detector that already exists.
    """
    if decision.action == "none":
        return
    await record_event(
        db,
        session,
        "context.off_track" if decision.action in {"wrong_application", "redirect"}
        else f"context.{decision.action}",
        request_id,
        {
            "step_id": step.id,
            "action": decision.action,
            "skippable": list(decision.skippable),
        },
    )
    if decision.action in {"wrong_application", "redirect"}:
        step.attempt_count += 1
        step.updated_at = m.now()
        await db.flush()
        if step.attempt_count >= OFF_TRACK_LIMIT and instruction is not None:
            await note_stuck(db, session, step, "off_track", request_id)
