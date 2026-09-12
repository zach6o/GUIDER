# ADR-001 · Standalone User Mode first

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

The supplied repository is empty. Kurukul's future User/Learner/Institutional modes are product context, not code here. Practical guidance needs a coherent release without waiting for courses or platform orchestration.

## Decision

Build Guide as standalone User Mode with independent web, backend and Windows applications. Backend owns its sessions and authenticated v1 APIs. Keep learning transitions behind a future authorization adapter; basic guidance must run without Learner Mode or Agent Zero availability.

## Alternatives considered

Build inside the full platform first: higher integration dependency and uncertain unavailable contracts. Throwaway desktop prototype: faster demonstration but costly identity/state/privacy replacement. A single embedded web/backend/native package: obscures deployment and trust boundaries.

## Consequences

Adds explicit API and identity contracts early; permits independent deployment and future reuse. No duplicated course/progress service. A future external repository must be inspected and reconciled rather than assumed compatible.

## Revisit conditions

An actual Kurukul integration contract and approved ownership model are available, or standalone boundaries prevent a validated requirement. Preserve User Mode availability even after integration.

## Assumptions, dependencies, security and open decisions

Assume this is the intended new workspace. Depends on 06/07/09 and ADR-013/014; D02 hosting remains open. SEC-01/16 enforce identity and cross-mode limits. Example: learning service outage cannot prevent a Python screenshot explanation.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R19/R26/R30 | F19/F26/F30; v1 Guide API; UX01/UX09 | SEC-01/16; T19/T26/T30; 0/1/future |

Master traceability: [17](../17-traceability-matrix.md).
