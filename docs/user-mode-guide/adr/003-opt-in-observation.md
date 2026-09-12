# ADR-003 · Observation is explicit and scoped

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Desktop content can include unrelated private work. Plan approval does not imply screen permission. Network calls cannot be relied on to stop local capture.

## Decision

Default observation off; allow one selected allowlisted app window and optional crop. Use local consent/OS picker, persistent indicator, user-triggered stills, short lease and grant expiry. Pause/stop/close/revoke immediately close local gate; new permission is required after resume. No continuous desktop monitoring.

## Alternatives considered

Always-on capture: unacceptable scope. Whole-display consent: excessive in MVP. Server-only stop: fails during outages. Restore prior grant after restart: obscures renewed user choice.

## Consequences

More explicit permission steps, smaller exposure and testable safety. Provider bytes already transmitted cannot necessarily be recalled; reject late results and disclose supplier retention. Denial must not block manual help.

## Revisit conditions

Whole-display/region support requires separate explicit product scope, privacy review and tests. Never weaken local stop or default-off semantics merely for convenience.

## Assumptions, dependencies, security and open decisions

Depends on native capture/lease/epoch implementation in 03–05/09; D03 OS certification. Assume interactive desktop, not background service. Example: Pause works even with no network.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R06/R11/R17 | F06/F11/F17; permissions/pause; UX05/UX07 | SEC-03/05/06; T06/T11/T17/T32; 4 |

Master traceability: [17](../17-traceability-matrix.md).
