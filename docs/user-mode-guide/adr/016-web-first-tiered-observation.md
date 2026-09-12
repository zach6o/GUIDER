# ADR-016 · Web-first guidance with tiered observation

Date: 2026-09-12 · Status: proposed for v2; supersedes the observation trigger in [003](003-opt-in-observation.md), the MVP overlay surface in [006](006-floating-windows-overlay.md) and the native-client phase position in [014](014-initial-stack-and-contracts.md). Extends [015](015-browser-observation-and-personal-cloud.md) from a local exception to the product direction. Does not weaken [004](004-no-raw-video-storage.md), [005](005-guide-not-control.md) or [012](012-high-risk-action-gates.md).

## Context

The product target is continuous step-by-step guidance while the user works: the user states a goal, shares one window, and Guider recognizes progress and supplies the next action without being asked. [003](003-opt-in-observation.md) specified user-triggered stills, which requires an explicit gesture per frame and cannot detect progress. [006](006-floating-windows-overlay.md) and [014](014-initial-stack-and-contracts.md) placed the guidance surface in a WPF client; `user-mode/client/windows` remains an empty scaffold, while the browser path in [015](015-browser-observation-and-personal-cloud.md) is implemented and exercised by tests. Naive continuous observation is not affordable or acceptable: a 1–2 second cadence produces 1,800–3,600 frames/hour, exceeding the 40-call session budget in [05](../05-session-state-machine.md)/[07](../07-api-contracts.md) within a minute and transmitting far more of the user's screen than the current design.

## Decision

Guidance is web-first. No Electron, Tauri, WPF or other native dependency is added. Observation uses a tiered admission model; raw frames are never streamed.

**T0 motion gate** runs in the browser every ~500 ms: the current video frame is drawn to a 64×64 grayscale canvas and compared to its predecessor by difference hash and mean absolute difference. Frames below threshold are discarded locally and never encoded.

**T1 settle and admit** runs in the browser: a detected change MUST hold steady for ~700 ms, the session MUST have a step awaiting action, and the admission rate limiter and session budget MUST allow it. The session mask from the existing editor is applied before encoding, so redacted regions never leave the machine.

**T2 observation** sends one admitted still to a vision provider, at most one per 4 seconds. Its output schema is `{step_complete, confidence, app_visible, ui_changed, anomaly, note}`. It MUST NOT return instruction text, locations or next actions.

**T3 reasoning** covers plan, instruction, verification, replan and explanation. It runs only on step advance, anomaly, stuck signal or explicit user request.

Per-session budgets replace the flat 40-call cap: 200 observation calls, 40 reasoning calls, 12 admitted frames/minute, 600 observation calls/owner/hour, 30 minutes of continuous observation wall clock. Budget exhaustion degrades to the existing user-triggered still path; it is a supported mode, not an error.

Observation frames are **never persisted**: not to object storage, not to the database, not to backups. They exist in volatile memory for one request. `source=observation` rows are not written. This is stricter than [004](004-no-raw-video-storage.md), not an exception to it.

Continuous observation requires its own consent, separate from single-frame review, naming the cadence, the budget and the provider. While it is on, the overlay MUST display a live count of frames sent this session, and a one-tap stop MUST increment `control_epoch`, revoking in-flight work through the existing mechanism. Default remains off; one selected window; full-display selection remains rejected; hiding the page, source loss, offline state, expiry and unmount still close tracks; resuming requires a fresh picker gesture.

The guidance surface is a floating in-page island, promoted to an always-on-top OS window through the Document Picture-in-Picture API where available, with side-by-side and mirrored-preview fallbacks as first-class modes. `user-mode/client/windows` is frozen and archived, not deleted.

## Alternatives considered

Send every frame: 1,800–3,600 frames/hour, unaffordable and disproportionate. Fixed-interval sampling without a change gate: pays for static screens and still misses fast changes. Server-side frame diffing: transmits discarded frames, defeating the purpose. Keep manual per-frame checks: cannot detect progress, so the product remains a screenshot analyzer. Electron or a native client for a true overlay: reintroduces the native dependency this decision removes and duplicates the capture path that already works.

## Consequences

The user no longer reviews each outgoing frame in continuous mode; they review the scope and the mask once, then monitor the counter. This is the material privacy change in this ADR and requires a `privacy_notice_version` bump and new consent copy before first use. Browser sharing still cannot attest executable identity, enforce the [011](011-application-allowlisting.md) allowlist, or exclude password fields before acquisition; those gates remain required before any distributed release, and continuous observation MUST stay unavailable in production until they exist. Automatic advancement becomes possible and introduces false-positive completion as the principal failure mode; mismatch rate MUST be instrumented from first implementation. Observation latency budget (~1 s) excludes the durable operation queue, so observation is a synchronous request whose only persisted artifact is its outcome event.

## Revisit conditions

Measured false-positive advancement exceeds calibration targets; a native client is separately authorized with its own capture and overlay certification; Document Picture-in-Picture becomes unavailable or is superseded; or provider pricing changes the tier boundaries materially. Never raise the observation cadence above the change gate, remove the frame counter or make observation the default merely for convenience.

## Assumptions, dependencies, security and open decisions

Assume a desktop Chromium browser, an interactive session and a user willing to share one window. Depends on [05](../05-session-state-machine.md) epochs and leases, [09](../09-security-and-privacy.md), the existing capture adapter and [ADR-017](017-provider-role-abstraction.md) for the observer provider. D01 gates any production observation provider; D06 must approve the continuous-observation notice; D03/D04 no longer gate the MVP path. SEC-03/04/05/09/12/14 apply unchanged: observation off by default, bounded media, immediate local stop, untrusted screen content, fail-closed, quotas. Example: a user reads documentation for two minutes; T0 admits nothing and no provider call is made.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R06/R07/R11/R12/R16/R21/R23 | F06/F07/F11/F16/F23; `POST /sessions/{id}/observe`; UX05/UX06/UX07/UX14 | SEC-03/04/05/09/12/14; T06/T11/T16/T21/T23/T32; v2 phase 3 |

Master traceability: [17](../17-traceability-matrix.md).
