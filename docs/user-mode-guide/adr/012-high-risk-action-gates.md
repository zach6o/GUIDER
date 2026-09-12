# ADR-012 · High-risk actions are blocked or specifically confirmed

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Deleting, sending, submitting, purchasing, publishing or changing security settings can have effects that a screenshot cannot reverse. Generic session approval is insufficient.

## Decision

SEC-07 blocks banking/payment, credentials, regulated submissions, CAPTCHA and high-risk administrative/security changes without override. Permitted ordinary high-risk guidance requires a fresh target/version/consequence-bound on-screen confirmation, as do concrete medium-risk changes. In all MVP cases the user performs the action; no automatic execution. Confirmation and verification are separate.

## Alternatives considered

Ask once at session start: not action-specific. Let model decide consent: unsafe and unverifiable. Block every modification: prevents useful ordinary setup. Enable execution after a dialog: violates initial scope.

## Consequences

Adds deliberate friction before consequential steps and requires challenge expiry/target-change handling. External communication tasks remain post-MVP where app support is absent. Blocked tasks cannot be unlocked by “I confirm.”

## Revisit conditions

A new action class needs explicit scope and safety evaluation; execution requires new product authorization plus ADR-005 replacement and tests.

## Assumptions, dependencies, security and open decisions

Depends on 07/09/10/13; D06 privacy notice, no unresolved risk enum. Example: changing Git push branch invalidates prior action confirmation.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R17/R29 | F17/F29; ActionConfirmation; UX13 | SEC-07/08/15; T17/T29/A08; 2/expansion |

Master traceability: [17](../17-traceability-matrix.md).
