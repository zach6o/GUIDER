# ADR-007 · Multiple domains with a limited MVP

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Guide is useful beyond coding, but supporting every app would multiply uncertain controls, verifiers and sensitive contexts before the core loop is validated.

## Decision

Document nine domains and their tasks. Certify six initial categories—Setup, Run, Debug, Understand, Test, Git and GitHub—in the named Windows developer/browser apps. Mark other task rows post-MVP/future and gate allowlisting by app/verifier tests.

## Alternatives considered

Coding-only product positioning: limits the future module unnecessarily. Universal app support immediately: untestable promise. App-specific throwaway flows: duplicates the shared guidance loop.

## Consequences

Shared state/evidence/permission loop supports later expansion. Users must see honest unsupported responses for listed future apps. Phase 6a certifies MVP apps; 6b adds Office/creative domains separately.

## Revisit conditions

Pilot evidence supports another bounded domain and its app/privacy/verifier acceptance pack passes; update taxonomy/API enum scope explicitly.

## Assumptions, dependencies, security and open decisions

Assume initial developer workflows are reproducible; validate under D05/D07. Depends on 01/10/15/16. Example: Excel formulas remain a future app pack even though the catalogue explains their goal/verifier.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R24/R25 | F24/F25; Category/app policy; UX02/UX08 | SEC-06/07; T24/T25; 0/6a/6b |

Master traceability: [17](../17-traceability-matrix.md).
