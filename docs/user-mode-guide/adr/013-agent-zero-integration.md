# ADR-013 · Future Agent Zero authorization boundary

Date: 2026-09-07 · Status: proposed interface design; future implementation.

## Context

Kurukul may connect practical difficulty to structured learning and coordinate Atlas, Builder, Detector and Scout. No platform contracts or agents exist locally.

## Decision

Keep a future versioned backend adapter for Agent Zero-authorized owner/purpose/mode/task scopes. Orchestrator remains the only Guide coordinator. Cross-mode handoff requires preview and user consent and carries only minimal redacted summary/skill tags. Screen/mic grants, tokens and raw media never transfer. Guide basic operation is independent of Learner/Agent Zero.

## Alternatives considered

Direct peer-agent calls: uncontrolled authorization/state changes. Shared unrestricted database: leaks mode boundaries. Require Agent Zero for every local Guide step: unnecessary availability dependency. Duplicate platform teaching roles: unclear ownership.

## Consequences

Atlas can later implement explanations, Builder practical expertise, Detector opt-in progress signals and Scout learning suggestions through existing role adapters. No automatic course enrollment, passive focus monitoring or MVP network endpoint is created.

## Revisit conditions

Real Agent Zero protocol, audience/scope/token authority and user-consent contract are supplied and reviewed. Add actual API schemas and contract tests before integration code.

## Assumptions, dependencies, security and open decisions

Assume future platform identity can map verified User ownership; this must be checked against real code. Depends on 06/09/12; future protocol deliberately unresolved, not an MVP gate. Example: a declined Python learning offer leaves current Guide task unchanged.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R19/R26 | F19/F26; future adapter; UX09 future handoff | SEC-16; T19/T26; 0 design/future implementation |

Master traceability: [17](../17-traceability-matrix.md).
