# ADR-020 · Two overlay surfaces, one mark vocabulary

Date: 2026-09-14 · Status: proposed for V2; refines [006](006-floating-windows-overlay.md) and the
deferral recorded in [016](016-web-first-tiered-observation.md). Does not alter
[005](005-guide-not-control.md) or [011](011-application-allowlisting.md).

## Context

V2 asks for visual guidance: an arrow on the Download button, a spotlight on a menu, a ring around
the field to type in. That is the difference between describing a control and showing it, and it is
the most valuable thing in the V2 brief.

A web page cannot draw on another application's window. No API grants it and no permission unlocks
it. Document Picture-in-Picture, which this product already uses, provides a floating window
*belonging to Guider* — not a transparent layer over the user's desktop. The honest options are to
draw marks somewhere a browser is allowed to draw, or to wait for the native client that
[016](016-web-first-tiered-observation.md) deferred.

Waiting means shipping no visual guidance at all for as long as the native client takes. Pretending
means an arrow that points at nothing.

## Decision

Define **two overlay surfaces** that consume **one mark vocabulary**.

| Surface | Draws on | Ships |
|---|---|---|
| **Preview overlay** | Guider's own mirrored copy of the shared window, in the island or the page | V2.3, in the browser |
| **Desktop overlay** | The user's real screen, over their real application | With the signed native client and its certification; not in this roadmap |

Marks are defined once, in **normalised `0..1` frame coordinates**, and validated server-side. The
renderer multiplies by whatever surface it draws into. A mark therefore survives DPI changes, zoom,
window moves, monitor swaps and the eventual move to the native surface without the instruction
contract changing at all.

Three rules travel with the vocabulary:

1. **Every mark has a text equivalent.** `where` must locate the control in words that work with no
   overlay. An overlay-only instruction is a defect, not a feature.
2. **Marks are advisory.** A mark that cannot be placed is logged and dropped; the guide continues.
   Guidance must never depend on geometry the product cannot guarantee.
3. **One primary mark per instruction.** One thing to do, one thing pointed at
   ([010](010-one-step-guidance.md)).

## Alternatives considered

**A browser extension with content scripts.** Could draw on web pages the user visits, and only
those. It would not help with a terminal, an editor or an installer — the applications this product
exists for — and it adds a distribution channel and a permission model for a fraction of the cases.
[018](018-imported-conversation-context.md) already refused an extension for import; the same
reasoning applies here.

**Ship no visual guidance until the native client exists.** Defensible, and it postpones the most
valuable part of V2 behind the largest piece of work in the programme, with nothing learned in the
meantime about whether users can act on marks at all.

**A transparent always-on-top browser window.** Not possible: the page cannot be click-through, and
an opaque window over the target is worse than no window.

## Consequences

The preview overlay asks the user to look at Guider's copy of their window, then act on their own —
a real cost in attention, and the reason the text equivalent is mandatory rather than encouraged.
It is also a genuine test bed: if marks on a mirror do not help people, marks on the desktop
probably will not either, and that is worth learning before building a native client.

The mark vocabulary being surface-independent is what makes the native overlay a renderer swap
rather than a re-specification.

## Revisit conditions

A browser gains a real desktop overlay capability; the native client is authorized, at which point
the desktop surface becomes primary and the preview becomes the fallback; measurement shows users
cannot act on preview marks, in which case the preview overlay is withdrawn rather than kept for
appearances.

## Assumptions, dependencies, security and open decisions

Assume the shared window is mirrored at a known size, so normalised coordinates map exactly. Depends
on [016](016-web-first-tiered-observation.md) and [019](019-context-engine.md) for the control boxes
marks point at. Marks carry no link and no markup, and geometry outside the frame is dropped
server-side. [011](011-application-allowlisting.md) is untouched and still governs the desktop
surface.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R07/R08/R21 | F07/F08; `Instruction.marks`; UX06 | SEC-03/09/15; T53; V2.3 |

Master traceability: [17](../17-traceability-matrix.md).
