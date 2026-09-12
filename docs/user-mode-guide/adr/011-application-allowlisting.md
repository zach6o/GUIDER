# ADR-011 · Application allowlisting

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

A selected desktop window may expose secrets or unsupported workflows. Executable identity alone cannot make all browser tabs safe. Vision is not a reliable first privacy gate.

## Decision

Live observation only for tested app identity/workflow policies and one explicitly selected window/crop. Revalidate scope/sensitivity before still acquisition and upload; block password/regulated/secure surfaces. Unknown browser origin or unreliable sensitive-field detection uses manually redacted screenshots instead. User/model text cannot add allowlist entries.

## Alternatives considered

Capture any window then cloud-classify: transmits private content too early. Window-title matching: spoofable and leaks titles. Allow all pages in an approved browser: ignores sensitive tabs.

## Consequences

Some legitimate screens require manual context and app-specific testing. Local metadata inspection stays minimal/read-only. Policy updates must be trusted/versioned; allowlisting never proves a compromised endpoint is safe.

## Revisit conditions

A new tested app/domain/version is ready with sensitive-surface and geometry/verifier fixtures. Broader display access requires separate ADR, not an allowlist wildcard.

## Assumptions, dependencies, security and open decisions

Depends on 03/04/09/10; D07 app versions and D03 OS behavior. Example: an allowed Edge process switches to a banking tab; observation stops instead of inheriting permission.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R17/R24 | F17/F24; ScreenObservationPermission/app policy; UX05/UX08 | SEC-03/06/07; T17/T24; 4/6 |

Master traceability: [17](../17-traceability-matrix.md).
