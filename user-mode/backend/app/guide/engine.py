"""The Guide Engine: the only writer of session state.

Every state change goes through `transition`, which checks the move against the
table in [05](../../../../docs/user-mode-guide/05-session-state-machine.md) and
rejects anything unlisted with `409 invalid_transition`. Provider results are
proposals; roles proposed them, the guard vetted them, and this module decides
whether the session may move.

The table is written out rather than derived, so a reviewer can compare it line
by line against doc 05. The rules below it cover the table's "any nonterminal"
rows, which would otherwise need every state repeated.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.errors import GuideError

TERMINAL = frozenset({"completed", "failed", "expired"})

# Transient states are never resume targets; `paused` and `blocked` return here.
CHECKPOINTS = frozenset({"task_created", "awaiting_user_confirmation", "awaiting_user_action"})

# Doc 05: "Working state" means these. Risk-gate failures during intake and
# planning may also block, which BLOCKABLE covers.
WORKING = frozenset(
    {
        "analyzing",
        "active",
        "capturing",
        "processing",
        "instruction_ready",
        "awaiting_user_action",
        "verifying",
    }
)
BLOCKABLE = WORKING | {
    "task_created",
    "plan_ready",
    "awaiting_user_confirmation",
    "awaiting_screen_permission",
}

ALL_STATES = frozenset(
    {
        "task_created",
        "analyzing",
        "plan_ready",
        "awaiting_user_confirmation",
        "awaiting_screen_permission",
        "active",
        "capturing",
        "processing",
        "instruction_ready",
        "awaiting_user_action",
        "verifying",
        "blocked",
        "paused",
        "stopping",
        *TERMINAL,
    }
)
NONTERMINAL = ALL_STATES - TERMINAL

# A plan or an analysis may be requested from these, per the 05 transition table.
ANALYSIS_STATES = frozenset({"task_created", "awaiting_user_confirmation", "paused", "blocked"})
PLAN_STATES = frozenset(
    {"task_created", "plan_ready", "awaiting_user_confirmation", "paused", "blocked"}
)

# The named rows of the 05 transition table, without its "any state" rows.
TRANSITIONS: dict[str, frozenset[str]] = {
    "task_created": frozenset({"analyzing"}),
    "analyzing": frozenset({"task_created", "awaiting_user_confirmation", "plan_ready"}),
    "plan_ready": frozenset({"awaiting_user_confirmation"}),
    "awaiting_user_confirmation": frozenset(
        {"analyzing", "awaiting_screen_permission", "active"}
    ),
    "awaiting_screen_permission": frozenset({"active"}),
    "active": frozenset({"capturing", "processing"}),
    "capturing": frozenset({"processing"}),
    "processing": frozenset({"instruction_ready", "verifying", "awaiting_user_action"}),
    "instruction_ready": frozenset({"awaiting_user_action"}),
    # `analyzing` is the replan row: a stuck or mismatched guide may ask for a
    # replacement roadmap, which lands as a draft for the user to confirm.
    "awaiting_user_action": frozenset(
        {
            "verifying",
            "capturing",
            "processing",
            "analyzing",
            "completed",
            "awaiting_user_confirmation",
        }
    ),
    "verifying": frozenset({"active", "awaiting_user_action", "completed"}),
    # Resume returns to a stable checkpoint, or asks for permission again. A
    # diagnostic analysis while paused or blocked runs as an Operation and does
    # not leave the state, so `analyzing` is deliberately not a target here.
    "paused": frozenset(CHECKPOINTS | {"awaiting_screen_permission"}),
    "blocked": frozenset(CHECKPOINTS | {"awaiting_screen_permission"}),
    "stopping": frozenset({"completed"}),
}


def allowed(current: str, target: str) -> bool:
    """Whether doc 05 permits this move."""
    if current in TERMINAL:
        return False  # Terminal is terminal; continuing creates a new session.
    if current == target:
        return True  # Same-state commands still advance state_version.
    if target in TERMINAL - {"completed"} and current != "stopping":
        return True  # Expiry and unrecoverable failure reach any nonterminal state.
    if target == "stopping":
        return True  # Stop, close, sign-out and deletion take priority.
    if target == "paused" and current != "stopping":
        return True
    if target == "blocked" and current in BLOCKABLE:
        return True
    # A material plan edit from a working state returns to confirmation.
    if target == "awaiting_user_confirmation" and current in WORKING:
        return True
    return target in TRANSITIONS.get(current, frozenset())


async def record_event(
    db: AsyncSession,
    session: m.GuideSession,
    kind: str,
    request_id: str,
    payload: dict | None = None,
) -> None:
    """Append one sequenced, content-free event for this session."""
    sequence = (
        await db.scalar(
            select(func.max(m.GuidanceEvent.sequence)).where(
                m.GuidanceEvent.session_id == session.id,
            )
        )
        or 0
    ) + 1
    db.add(
        m.GuidanceEvent(
            owner_id=session.owner_id,
            session_id=session.id,
            sequence=sequence,
            state_version=session.state_version,
            control_epoch=session.control_epoch,
            type=kind,
            request_id=request_id,
            payload=payload or {},
            expires_at=m.now() + timedelta(days=7),
        )
    )
    await db.flush()


async def transition(
    db: AsyncSession,
    session: m.GuideSession,
    target: str,
    reason: str,
    request_id: str,
) -> None:
    """Commit a state change, or refuse it.

    Nothing else in the application may write `GuideSession.state`.
    """
    previous = session.state
    if not allowed(previous, target):
        raise GuideError(
            409,
            "invalid_transition",
            "That is not a step this task can take right now.",
        )
    session.state = target
    session.state_version += 1
    session.updated_at = m.now()
    if previous != target:
        await record_event(
            db,
            session,
            "session.state_changed",
            request_id,
            {
                "from": previous,
                "to": target,
                "reason": reason,
                "state_version": session.state_version,
                "control_epoch": session.control_epoch,
            },
        )
