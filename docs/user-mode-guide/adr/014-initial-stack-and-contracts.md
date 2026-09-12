# ADR-014 · Initial stack and contracts for the empty repository

Date: 2026-09-07 · Status: adopted for the first development slice. Exact Python/web dependency versions are pinned in `user-mode/backend/uv.lock` and `user-mode/web/package-lock.json`. Release/provider decisions and native validation remain open; see [19](../19-implementation-status.md).

## Context

Inspection found no code, approved framework, dependency lockfile, deployment config or legacy contract. A coding agent still needs concrete service boundaries and defaults. Windows capture/overlay behavior is central and security-sensitive.

## Decision

Propose React/TypeScript/Vite web, FastAPI/Pydantic backend with SQLAlchemy/Alembic and PostgreSQL, C#/.NET WPF native client with Win32/Windows.Graphics.Capture interoperability, Supabase Auth and private object storage adapter. Keep independent build/deploy entrypoints in the three named directories. Use REST JSON `/api/v1/guide`, bounded async Operations and authenticated SSE; PostgreSQL outbox/worker, no broker requirement in MVP. Local suggested ports 5173/8000/5432 are new defaults. SDK/model versions and cloud are not yet pinned.

## Alternatives considered

Next.js: useful if server rendering/BFF becomes required, not necessary for this small authenticated static frontend. Electron/Tauri: web UI reuse but additional native capture/focus/auth bridge complexity. WinUI 3: viable alternative but must prove runtime/Windows support and overlay interop. SQLite production: simpler single-process setup but does not meet proposed multi-worker ownership/concurrency/recovery baseline. Independent microservice per agent: avoidable operational burden.

## Consequences

Three toolchains require build documentation and contract generation. Native spike must prove OS picker, WPF geometry, click-through, accessibility and disposal; otherwise revise this ADR before broad native implementation. Production PostgreSQL integration tests are necessary; SQLite unit tests cannot substitute. No auth/provider package is claimed installed or secure merely by selection.

## Revisit conditions

An actual upstream repository supplies preserved contracts, native spike fails, team/platform constraints materially change, or deployment requirements justify a different stack. Record evidence and update 04/06/07/08/tests together, preserving Supabase/safety decisions unless separately authorized.

## Assumptions, dependencies, security and open decisions

D01–D04 select providers/hosting/platform/signing; D05–D07 validate release. Depends on all core contracts and inspection report. SEC-01/02/11/15 governs toolchains. Example: choosing a framework must not introduce browser-to-provider calls or a local command-execution endpoint.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R15/R19/R20/R30 | F15/F19/F20/F30; v1 API/Operation; UX01/UX14 | SEC-01/02/11/15; T15/T19/T20/T28/T30; 0/1/3 |

Master traceability: [17](../17-traceability-matrix.md).
