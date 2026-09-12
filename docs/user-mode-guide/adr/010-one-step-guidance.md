# ADR-010 · One verified step at a time

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Long instruction lists overwhelm users and quickly diverge from current UI. A user's Done statement is different from observable success.

## Decision

Show the whole proposed plan for approval, then one current actionable instruction. Include what/where/why when useful/how to check/cannot-find alternative. Record CompletionClaim separately from VerificationResult; advance only with appropriate evidence or label self-reported completion distinctly. Correct mismatches before proceeding.

## Alternatives considered

Large answer dump: difficult to follow/verify. Auto-advance on timer or click: no result evidence. Treat user confidence as objective success: misleading metric and poor recovery.

## Consequences

More short interactions, clearer progress and less speculative context. User can still inspect plan/history or request deeper explanation. Understand tasks may end user_reported, not mastery-certified.

## Revisit conditions

Evidence supports optional batching of low-risk instructions without losing checkpoints/accessibility; any change must preserve verification semantics.

## Assumptions, dependencies, security and open decisions

Depends on 02/05/07/11/13; D05 clarity/verification calibration. Example: a screenshot showing a typed command does not prove successful execution.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R08/R09/R10 | F08/F09/F10; Instruction/CompletionClaim/VerificationResult; UX06 | SEC-05/09; T08/T09/T10; 2/4 |

Master traceability: [17](../17-traceability-matrix.md).
