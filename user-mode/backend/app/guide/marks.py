"""Where to point, when the guide can see the screen.

An instruction says what to do and where to look. A mark says *there* — a ring
around the button, a spotlight on the menu — and that is the difference between
describing a control and showing it.

**Marks are derived here, not asked for.** The instruction role never sees a
screen; asking it for geometry would be asking it to invent coordinates. The
observer did see one, and reported the controls it found with normalised boxes.
So a mark is produced by matching the instruction's own words against those
controls, at the moment the frame was read. This also settles staleness: a mark
belongs to the tick that saw the control, so a window that moved between frames
cannot leave an old mark pointing at empty space
([ADR-020](../../../../docs/user-mode-guide/adr/020-overlay-surfaces.md)).

Three rules the renderer must be able to rely on, enforced here rather than
there:

1. **Normalised, always.** `0..1` against the frame, clamped. The renderer
   multiplies by whatever surface it draws into, so DPI, zoom, a moved window and
   the eventual native overlay change the multiplier and never the mark.
2. **One primary mark.** One thing to do, one thing pointed at (ADR-010).
3. **A mark is advisory.** No match is the normal case, not a failure: the
   instruction's own `where` locates the control in words, and an overlay-only
   instruction would be a defect.
"""

import re
from dataclasses import dataclass

from app.guide.guard import restricted_action

# A box smaller than this in either dimension is noise — a stray detection, or a
# control too small to ring usefully.
MIN_SIDE = 0.01

# How much of the instruction's wording must appear in a control's label before
# the match counts. Deliberately strict: a wrong arrow is worse than none.
MIN_TOKEN_OVERLAP = 1

# Words that carry no identifying weight, so they never count toward a match.
_NOISE = frozenset(
    {
        "the", "a", "an", "and", "or", "to", "in", "on", "at", "of", "for", "with",
        "your", "you", "it", "this", "that", "then", "click", "press", "select",
        "choose", "open", "type", "enter", "button", "menu", "window", "screen",
    }
)


@dataclass(frozen=True)
class Mark:
    """One thing to draw. `label` is what a screen reader is given, so it is
    never optional and never the empty string."""

    kind: str
    box: tuple[float, float, float, float]
    label: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "box": list(self.box), "label": self.label}


def tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in _NOISE}


def clamp(box) -> tuple[float, float, float, float] | None:
    """A box inside the frame, or nothing.

    Marks arriving from a provider are untrusted like everything else it says: a
    box that runs off the frame, inverts, or collapses to a line is dropped
    rather than drawn somewhere approximate.
    """
    try:
        left, top, right, bottom = (float(value) for value in box)
    except (TypeError, ValueError):
        return None
    left, top = max(0.0, min(1.0, left)), max(0.0, min(1.0, top))
    right, bottom = max(0.0, min(1.0, right)), max(0.0, min(1.0, bottom))
    if right - left < MIN_SIDE or bottom - top < MIN_SIDE:
        return None
    return (round(left, 4), round(top, 4), round(right, 4), round(bottom, 4))


def best_control(instruction_words: set[str], controls):
    """The control this instruction is most plausibly about, or nothing.

    Scored by how much of the instruction's own vocabulary appears in the label,
    with ties broken toward the shorter label — "Download" beats "Download the
    beta installer for developers" for an instruction that says download.
    """
    best, best_score = None, 0
    for control in controls:
        label_words = tokens(control.label)
        if not label_words:
            continue
        overlap = len(instruction_words & label_words)
        if overlap < MIN_TOKEN_OVERLAP:
            continue
        if overlap > best_score or (
            overlap == best_score and best is not None and len(control.label) < len(best.label)
        ):
            best, best_score = control, overlap
    return best


def kind_for(control) -> str:
    """What shape suits this control. A field gets an underline, a dialog gets a
    spotlight, everything else gets a ring."""
    return {"field": "underline", "dialog": "spotlight", "link": "pointer"}.get(
        control.kind, "circle"
    )


def mark_for(instruction, context) -> Mark | None:
    """One mark for this instruction against this screen, or none at all.

    None is an ordinary outcome. The instruction still says where to look in
    words, and a guide that pointed confidently at the wrong control would be
    worse than one that did not point.
    """
    if instruction is None or not context.controls:
        return None
    words = tokens(f"{instruction.what} {instruction.where or ''}")
    if not words:
        return None
    control = best_control(words, context.controls)
    if control is None:
        return None
    if restricted_action(control.label):
        # The guard already drops these from a context; this is the second gate,
        # because a mark is the one output that would put Guider's finger on it.
        return None
    box = clamp(control.box)
    if box is None:
        return None
    return Mark(kind=kind_for(control), box=box, label=control.label)
