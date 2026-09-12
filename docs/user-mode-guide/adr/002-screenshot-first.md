# ADR-002 · Screenshot-first support

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Users can provide a problem image before granting observation or installing native software. Visual evidence is necessary for targeted guidance, but screen access should not be required for basic help.

## Decision

Implement manual screenshot upload, preview/crop/redaction, explanation, viewer highlight and deletion before live observation. Reuse the same Screenshot and verification contracts later. Denied observation permission remains a supported screenshot-only path.

## Alternatives considered

Live-only: creates unnecessary permission/platform dependency. Text-only: misses visual UI/error context. Separate temporary screenshot service: duplicates privacy and evidence contracts.

## Consequences

Phase 1 provides useful testable behavior; images still carry privacy risks and need real lifecycle controls. Screenshot coordinates cannot be projected onto the live desktop without a native mapping. Not every screenshot proves success.

## Revisit conditions

Additional input formats/file consent are needed, or a tested task cannot work with stills. Do not remove manual mode merely because live capture exists.

## Assumptions, dependencies, security and open decisions

Assume users can crop relevant context. Depends on 03/07/08; D01 provider/D02 storage/D06 notice review. SEC-04/14 bounds media. Example: a Python traceback gets an in-image highlight without starting desktop observation.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R03/R06/R24 | F03/F06/F24; screenshots/analyses; UX03 | SEC-04/14; T03/T06/A01/A05; 1 |

Master traceability: [17](../17-traceability-matrix.md).
