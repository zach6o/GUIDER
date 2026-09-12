# ADR-009 · Persist task and session checkpoints

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

Users pause, close applications and lose network. Keeping only model conversation memory would lose progress and make verification/consent recovery ambiguous.

## Decision

Persist owner-scoped task/session/plan/step/claim/verification/summary plus state version, epoch and stable checkpoint. Use PostgreSQL transactions and durable operation/outbox records. Resume never restores screen grants. Terminal continuation creates a new linked session. Retain content under 08 deadlines, not indefinitely.

## Alternatives considered

In-memory sessions: fragile restarts. Persist raw chat/video: unnecessary privacy risk and poor explicit state. Client-only persistence: difficult cross-device authorization/concurrency.

## Consequences

Requires migrations, retention jobs and conflict rules. Separates claim from verification and history from current visible state. Expired image evidence cannot support a new recheck.

## Revisit conditions

Offline or enterprise requirements need different storage; preserve owner/epoch/retention semantics and demonstrate recovery safety before migration.

## Assumptions, dependencies, security and open decisions

Depends on 05/07/08/14, D02 storage/backup and D06 notice. Example: restart displays paused checkpoint, not an automatically active capture session.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R13/R14/R20 | F13/F14/F20; GuideSession/Operation; UX07/UX11 | SEC-05/12/13; T13/T14/T20/T33; 1/2/5 |

Master traceability: [17](../17-traceability-matrix.md).
