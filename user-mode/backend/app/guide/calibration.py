"""How often the observer was wrong, measured rather than assumed.

`ADVANCE_AT = 0.85` is a hypothesis. Doc 20 lists false-positive advancement as
the principal failure mode and D05 as the decision that has to close before
launch, and neither can be settled by argument: it needs counts from real
sessions. This module produces them.

Everything here is derived from `GuidanceEvent` rows, because frames are never
persisted and there is nothing else to read. That has two consequences worth
stating rather than discovering later. Events expire after seven days, so a
report covers a window and not all history. And silence is not proof: an advance
nobody contradicted is *unchallenged*, not confirmed, since most users will never
file feedback. The report says `unchallenged` for exactly that reason — a rate
computed as `contradicted / advances` would read as an error rate, and would be
one only if every wrong advance were reported.

The pairing is deliberately simple and explained where it happens, so a reviewer
can tell what the numbers mean before trusting them.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.observation import ADVANCE_AT, ASK_AT

BUCKET = 0.05


def bucket_of(confidence: float) -> float:
    """Lower edge of the 0.05 band this confidence falls in.

    Rounded to two places because these are dictionary keys: binary floating
    point turns 0.85 into 0.8500000000000001 and would split one band in two.
    """
    return round(min(0.95, max(0.0, int(round(confidence / BUCKET, 6)) * BUCKET)), 2)


@dataclass
class Bucket:
    lower: float
    advances: int = 0
    asks: int = 0
    waits: int = 0
    contradicted: int = 0

    @property
    def upper(self) -> float:
        return round(self.lower + BUCKET, 2)


@dataclass
class Report:
    """Counts, and the two things a reader needs to interpret them: what was
    observed, and what was never checked."""

    ticks: int = 0
    advances: int = 0
    asks: int = 0
    waits: int = 0
    # An advance the user later called wrong: the only hard evidence of a false
    # positive that exists.
    contradicted: int = 0
    # An ask the user answered, and an ask that was overtaken by another tick on
    # the same step, which means it was not answered at the time.
    asks_confirmed: int = 0
    asks_unconfirmed: int = 0
    buckets: dict[float, Bucket] = field(default_factory=dict)
    sessions: int = 0

    def bucket(self, confidence: float) -> Bucket:
        lower = bucket_of(confidence)
        return self.buckets.setdefault(lower, Bucket(lower=lower))

    @property
    def unchallenged(self) -> int:
        return self.advances - self.contradicted

    def threshold_effect(self, candidate: float) -> dict:
        """What moving the advance line to `candidate` would have done to the
        ticks actually observed: how many advances survive, how many known-wrong
        ones fall below it, and how many asks would have advanced instead."""
        kept = excluded_bad = promoted = 0
        for bucket in self.buckets.values():
            if bucket.lower >= candidate:
                kept += bucket.advances
                promoted += bucket.asks
            else:
                excluded_bad += bucket.contradicted
        return {
            "candidate": round(candidate, 2),
            "advances_kept": kept,
            "known_bad_excluded": excluded_bad,
            "asks_promoted": promoted,
        }


def build(events: Iterable[dict]) -> Report:
    """Fold one session's events, oldest first, into a report.

    `events` are plain `{type, payload}` dicts so this runs over an export and is
    testable without a database.
    """
    report = Report(sessions=1)
    # The last unanswered question per step.
    open_asks: dict[str, float] = {}

    for event in events:
        kind = event.get("type")
        payload = event.get("payload") or {}
        step_id = payload.get("step_id")

        if kind == "observation.tick":
            decision = payload.get("decision")
            confidence = float(payload.get("confidence") or 0.0)
            report.ticks += 1
            bucket = report.bucket(confidence)
            if decision == "advance":
                report.advances += 1
                bucket.advances += 1
            elif decision == "ask":
                report.asks += 1
                bucket.asks += 1
                if step_id:
                    if step_id in open_asks:
                        # Asked again on the same step: the earlier question went
                        # unanswered.
                        report.asks_unconfirmed += 1
                    open_asks[step_id] = confidence
            else:
                report.waits += 1
                bucket.waits += 1
            continue

        if kind == "verification.completed":
            # One event covers both arms, told apart by what it says. A
            # `user_reported` result after a question is the user answering it;
            # a pass is the observer resolving the step itself on a later frame,
            # which is not a user answer either way.
            if payload.get("status") == "user_reported" and step_id in open_asks:
                report.asks_confirmed += 1
            open_asks.pop(step_id, None)
            continue

        if kind == "verification.contradicted":
            confidence = payload.get("confidence")
            if confidence is not None:
                report.contradicted += 1
                report.bucket(float(confidence)).contradicted += 1
            continue

    # A question still open when the events run out was never answered.
    report.asks_unconfirmed += len(open_asks)
    return report


def merge(reports: Sequence[Report]) -> Report:
    total = Report(sessions=len(reports))
    for one in reports:
        total.ticks += one.ticks
        total.advances += one.advances
        total.asks += one.asks
        total.waits += one.waits
        total.contradicted += one.contradicted
        total.asks_confirmed += one.asks_confirmed
        total.asks_unconfirmed += one.asks_unconfirmed
        for lower, bucket in one.buckets.items():
            into = total.buckets.setdefault(lower, Bucket(lower=lower))
            into.advances += bucket.advances
            into.asks += bucket.asks
            into.waits += bucket.waits
            into.contradicted += bucket.contradicted
    return total


async def for_owner(db: AsyncSession, owner_id: str) -> Report:
    """Every session this owner has events for, inside the event retention
    window. Owner-scoped like everything else: there is no cross-owner read."""
    rows = list(
        await db.scalars(
            select(m.GuidanceEvent)
            .where(m.GuidanceEvent.owner_id == owner_id)
            .order_by(m.GuidanceEvent.session_id, m.GuidanceEvent.sequence)
        )
    )
    per_session: dict[str, list[dict]] = {}
    for row in rows:
        per_session.setdefault(row.session_id, []).append(
            {"type": row.type, "payload": row.payload}
        )
    return merge([build(events) for events in per_session.values()])


def render(report: Report) -> str:
    """A plain-text table. This is a calibration instrument for D05, not a
    product surface, so it prints rather than answering a client."""
    lines = [
        f"sessions {report.sessions}  ticks {report.ticks}  "
        f"advance {report.advances}  ask {report.asks}  wait {report.waits}",
        f"advances contradicted by the user: {report.contradicted} "
        f"(unchallenged {report.unchallenged}; silence is not confirmation)",
        f"asks answered {report.asks_confirmed}  unanswered {report.asks_unconfirmed}",
        "",
        "        band   advance   ask  wait  wrong",
    ]
    for lower in sorted(report.buckets, reverse=True):
        b = report.buckets[lower]
        lines.append(
            f"  {b.lower:>4.2f}-{b.upper:<4.2f}  {b.advances:>8}{b.asks:>6}"
            f"{b.waits:>6}{b.contradicted:>7}"
        )
    lines += ["", f"current thresholds: advance {ADVANCE_AT}, ask {ASK_AT}", ""]
    for candidate in (0.75, 0.80, 0.85, 0.90, 0.95):
        effect = report.threshold_effect(candidate)
        lines.append(
            f"  at {effect['candidate']:.2f}: {effect['advances_kept']} advances kept, "
            f"{effect['known_bad_excluded']} known-wrong excluded, "
            f"{effect['asks_promoted']} asks would advance"
        )
    return "\n".join(lines)
