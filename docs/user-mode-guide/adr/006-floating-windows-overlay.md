# ADR-006 · Floating Windows overlay

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Guidance should stay available while users work in another app without blocking content or stealing focus. A browser tab alone cannot provide a reliable native pointer/control surface.

## Decision

Use a draggable screen-edge dot, compact panel/readable instruction card and separate click-through pointer window. Dot may become subtle after 15 s; text and privacy indicators never fade. Keyboard controls, stop/close, multi-monitor/DPI transforms and normal mouse/keyboard access are mandatory. Stopped sessions remove all overlays.

## Alternatives considered

Full-screen overlay: risks input obstruction. Large always-open sidebar: covers work. Tray-only control: hides privacy state. Pointer that moves actual cursor: violates guidance-only policy.

## Consequences

Requires native accessibility/focus/geometry testing and separate window hit-testing. UI remains compact but details can expand on request. Monitor changes invalidate stale markers.

## Revisit conditions

Usability testing shows dot discoverability/accessibility problems; change presentation while preserving readable instruction and always-reachable stop.

## Assumptions, dependencies, security and open decisions

Depends on 03/04/11 and ADR-014. D03/D04/D07 govern support/signing/accessibility. Example: drag dot away from an editor button without changing actual cursor control.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R07/R12/R21/R27 | F07/F12/F21/F27; Instruction.pointer; UX06/UX14 | SEC-03/15; T07/T12/T21/T27; 3/4 |

Master traceability: [17](../17-traceability-matrix.md).
