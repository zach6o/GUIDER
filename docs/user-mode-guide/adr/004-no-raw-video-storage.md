# ADR-004 · No raw screen-video storage

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

The guidance loop needs relevant still evidence, not a permanent record of desktop activity. Video greatly increases privacy, storage, deletion and breach impact.

## Decision

Do not record/store raw screen video by default or offer a video-recording feature in MVP. Acquire one requested frame in volatile memory, close capture resources, store only redacted normalized stills for ≤24 h. Exclude media/audio from backups. Keep minimal verified-step facts with unavailable-evidence labels after expiry.

## Alternatives considered

Full recording for replay: broad retention burden. Permanent screenshots: unnecessary default. No persisted stills at all: more fragile bounded asynchronous analysis; may be revisited with a reviewed architecture.

## Consequences

Reduces context replay and requires new evidence for later rechecks. Retention workers must scrub derived image text and operation refs, not just objects. No supplier zero-retention promise is inferred.

## Revisit conditions

A separately approved recording use case and explicit user opt-in/retention model exist. Such a feature is outside this MVP and cannot be enabled by extending screenshot TTL silently.

## Assumptions, dependencies, security and open decisions

Depends on 03/08/09 lifecycle workers; D01/D02/D06 supplier/storage/notice review. Example: history shows verification time after image expiry, not an old thumbnail.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R16/R23 | F16/F23; Screenshot/DeletionJob; UX10/UX11 | SEC-04/10/13; T16/T23/T34; 1/4 |

Master traceability: [17](../17-traceability-matrix.md).
