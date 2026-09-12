# 15 · MVP implementation plan

Accepted exception to phase order: [ADR-015](adr/015-browser-observation-and-personal-cloud.md) authorizes the local browser observation and personal OpenAI workflow. Its implementation and validation are tracked in [19](19-implementation-status.md). This does not certify native phase 4 or remove any production release gate.

Proposed re-sequencing: [20](20-guide-engine-migration-plan.md) supersedes the order of phases 2–5 below if approved, moving the Task Planner and verification loop ahead of the native client and replacing native observation with the tiered browser observer of [ADR-016](adr/016-web-first-tiered-observation.md). Phase and exit-gate content below is retained, not deleted; phase 3 native overlay work is deferred, and no production release gate is removed. Until that plan is approved, this document remains the active order.

Status: original proposed plan, now **phase 0/1 partially implemented**. See [19](19-implementation-status.md) for current scope and remaining gates; no phase is certified complete. Build sequential vertical slices and keep three services independently buildable. Do not implement later phases early unless future inspection proves supporting code already exists.

## Phase gates and deliverables

| Phase | Implement when separately authorized | Dependencies / exit gate |
|---|---|---|
| 0 · Documentation and repository alignment | Reinspect repository; accept ADR baseline; pin stack versions; produce OpenAPI/JSON Schema from 07 and migration design from 08; establish independent web/backend/native build manifests when coding starts; validate native PKCE feasibility using synthetic auth environment | Docs/links/enums/traceability coherent; no legacy contracts invented; D01/D02 staged decisions recorded; exact app/OS fixture candidates listed; no media to unreviewed provider |
| 1 · Screenshot Help | Supabase web sign-in and JWT/owner middleware; task+session creation; private upload/preview/crop/redaction/deletion; bounded decoder; provider adapter/test double; analysis explanation and viewer boxes; persistence, operation polling, quotas, lifecycle jobs and audit | T01–T04/T15/T16/T18/T19/T23/T28/T30/T31/T34/T35 pass; Python error screenshot fixture works; cross-owner access fails; deletion really removes bytes/derived context; production media gated D01/D02/D06 |
| 2 · Task Planner | Plan generation/edit/reorder/version/confirmation; instruction schema and screenshot-only step loop; completion claim, verification, feedback and summary | Phase 1; T05/T08–T10/T14/T17/T20/T24/T29 pass; stale confirmation rejected; unsafe actions blocked; deterministic summary fallback; no claim-only achieved result |
| 3 · Windows Overlay | Native Supabase login/device storage; floating dot/panel/pointer rendering against synthetic geometry; privacy controls and permission indicator; keyboard/DPI/multi-monitor; packaging and crash-safe in-process lifecycle | Phase 2; D03/D04/D07 decisions; T07/T12/T15/T21/T27/T36/T37; native spike proves capture API availability and disposal, but no live media feature until phase 4 |
| 4 · Live Observation and Verification | OS picker, local consent, allowlist, demand-driven still acquisition, crop/secret gate, lease/epoch/controller, authenticated SSE, fresh geometry mapping, user-triggered verification | Phase 3; T06/T09/T11/T17/T20–T23/T31–T33/T36/T37; pause/stop/revoke racing capture/upload/provider result pass; no capture from unapproved window or stale grant |
| 5 · Voice and Session Recovery | Push-to-talk, codec limits, editable transcript and command; full pause/resume/history/continue after crash/network/restart, controller transfer and expiry UI | Phase 4; D01 speech review; T04/T13/T14/T22/T32/T33/T36/T37; voice never authorizes risk/capture; all ten required acceptance scenarios pass |
| 6a · MVP application certification | Complete regression packs for VS Code, PowerShell/Windows Terminal, Chrome/Edge, Git/GitHub, Python/JS/TS and basic Docker Desktop across supported releases | Phases 1–5; T24/T28/T31, privacy regression and D05/D07 pilot evaluation; this certifies MVP, not broad app expansion |
| 6b · Post-MVP expansion | Add Office applications, Google Docs/Sheets, broader Windows troubleshooting and then creative app packs, one domain at a time | New taxonomy/API enum/app allowlist/verifier tests and scope review; no bundled execution tools; future enterprise/3D work requires separate approval |

The user-proposed phase labels are retained; 6a/6b resolve the overlap between initial app support and later supported-application expansion. Initial app fixtures must be used from phase 1, not deferred until after development. Foundational pause/stop/state/retention controls are built as early as their feature requires; phase 5 completes recovery UX, it does not postpone safe pause or persistence.

## First coding slice

Recommended first coding task: scaffold the independently buildable web/backend boundaries and implement **authenticated task creation plus one private screenshot analysis flow using a deterministic provider adapter**, including actual media deletion and owner-isolation tests. Generate the relevant OpenAPI schemas first; do not start with a desktop overlay or multi-agent framework. Integrate a reviewed real vision provider only after this slice works with synthetic data and D01/D02/D06 are resolved.

Deliverable PR scope: build manifests/lockfiles, Supabase configuration placeholders, auth middleware, initial User/GuideTask/GuideSession/Screenshot/Operation/AnalysisResult migrations, upload limits/private storage abstraction, image preview/deletion, viewer markers, contract and authorization tests, documented local startup. Avoid creating unimplemented future API handlers that return fake success. Public URLs/model keys are configuration, never committed secrets.

## Work organization, estimates and dependencies

Planning estimate, not commitment: 2–3 experienced implementers plus part-time UX/security/QA, roughly 10–16 engineering weeks across phases 0–6a after access/procurement. Phase 0 1 week; phase 1 2–3; phase 2 1–2; phase 3 2–3; phase 4 2–3; phase 5 1–2; certification 1–2, with some verification/UX overlap. Reestimate after native/auth spike and provider pilot. Required capabilities: web/backend, Windows capture/overlay engineering, security review, test automation and product acceptance ownership. This is resource planning, not an instruction to spawn agents.

Dependency chain: contract/schema → identity/ownership → media/deletion → analysis → confirmed plans → instruction/verification → native auth/overlay → local consent/capture → resilient sessions/voice → app certification. Keep provider/storage adapters replaceable; do not create Agent Zero/Atlas/Scout services in MVP. Database migrations must be forward-compatible and tested against PostgreSQL; record destructive migration/contract changes in ADRs.

## Release and rollback

Per-phase feature flags default off until acceptance; fail startup if unsafe production configuration. Roll back a feature by disabling its entrypoint and revoking active grants, without deleting task history or rolling back data destructively. Native signed update only while idle. Deploy backend contract-compatible changes before dependent clients; advertise minimum supported client version and return a safe update-required response for incompatible clients. Do not update an active session silently.

MVP release evidence: complete T01–T40 report, Windows hardware/app matrix, redaction/privacy demo, owner-isolation tests, deletion receipt and storage inspection, provider terms/disclosure, signed installation/update verification, pilot outcome/latency report, no unresolved release blockers. Product task success rates are measured, not assumed from passing API tests.

## Assumptions, open decisions and traceability

No existing dependencies, services or budgets are approved by repository code. D01/D02/D06 gate cloud pilot, D03/D04 gate Windows distribution, D05/D07 gate release claims. Security SEC-01–SEC-16 is built with each feature. Example: phase 1 explains a Python error in a screenshot viewer; it does not capture VS Code or start voice recording. Every phase maps to requirement and test IDs in [17](17-traceability-matrix.md).
