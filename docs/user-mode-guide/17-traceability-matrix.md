# 17 · Traceability matrix

Implementation evidence update: [19 · First development slice](19-implementation-status.md) maps the initial code and tests to these targets. Rows below remain the full normative release requirements; no phase is marked complete by the development slice.

Status: proposed implementation baseline. This matrix is authoritative for requirement coverage, not proof of implemented functionality. Requirement text is in [01](01-product-requirements.md), functional definitions in [02](02-functional-specification.md), routes in [07](07-api-contracts.md), entities in [08](08-data-model.md), UX IDs in [11](11-ux-specification.md), security rules in [09](09-security-and-privacy.md) and tests in [16](16-testing-strategy.md). Route paths below omit the common `/api/v1/guide` prefix.

| Product requirement | Functional requirement | API or data model | UI behavior | Security rule | Test case | Implementation phase |
|---|---|---|---|---|---|---|
| R01 Simple entry | F01 Homepage | POST /tasks; GuideTask | UX01 | SEC-01/04 | T01/T39 | 1 |
| R02 Goal/context | F02 Task creation | POST /tasks; GuideTask/GuideSession | UX02 | SEC-01/07 | T02/T47 | 1 |
| R03 Screenshot lifecycle | F03 Upload/replace/delete | POST /tasks/{task_id}/screenshots; DELETE /screenshots/{screenshot_id}; Screenshot/AnalysisResult | UX03 | SEC-04/14 | T03/T04/T34 | 1 |
| R04 Text/voice | F04 Input | POST /sessions/{session_id}/commands; POST /sessions/{session_id}/voice-inputs; UserCommand/VoiceInput | UX12 | SEC-04/08/10 | T04/T22/A09 | 1 text, 5 voice |
| R05 Confirmed plan | F05 Planning | POST /tasks/{task_id}/plans; PATCH plan; POST plan confirmations; TaskPlan/TaskStep | UX04 | SEC-07/08 | T05/T45/T47/A12 | 2 |
| R06 Optional screen access | F06 Startup | POST session start/permissions/decisions/captures; ScreenObservationPermission/CaptureIntent | UX05/UX10 | SEC-03/06 | T06/T20/T41/T42/T43/A05/A11 | 1 manual, 4 live |
| R07 Native pointer/dot | F07 Overlay | GET current instruction; Instruction.pointer | UX06/UX14 | SEC-03/15 | T07/T21/T49 | 3/4 |
| R08 One instruction | F08 Display | POST /sessions/{session_id}/instructions; Instruction | UX06 | SEC-07/09 | T08/T44/A02 | 2/3 |
| R09 Evidence verification | F09 Claim/check | POST completion-claims/verifications; CompletionClaim/VerificationResult | UX06/UX09 | SEC-05/09 | T09/T44/T48/A01/A10/A13 | 2/4 |
| R10 Adapt/correct | F10 Recheck/revision | POST feedback/retries; UserFeedback/VerificationResult | UX08 | SEC-05/09 | T10/T45/A06/A13 | 2/4 |
| R11 Pause/emergency | F11 Pause | POST pause; Permission/Session.control_epoch | UX07 | SEC-03/05/12 | T11/T32/T43/A03/A11 | 2 base, 4 live, 5 recovery |
| R12 Stop/terminate | F12 Stop | POST stop; GuideSession/SessionSummary | UX09/UX14 | SEC-05/12/15 | T12/T43/A04 | 2/3/4 |
| R13 Persist/resume | F13 Recovery | POST resume; POST /tasks/{task_id}/sessions; GuideSession.previous_session_id | UX07/UX11/UX14 | SEC-01/05/12 | T13/T32/T33/A07 | 2 persistence, 5 recovery |
| R14 History/summary/feedback | F14 History | GET sessions/summary; POST feedback; SessionSummary/UserFeedback | UX09/UX11 | SEC-01/04/13 | T14/T48/A10/A13 | 2/5 |
| R15 Supabase/ownership/devices | F15 Identity | POST/DELETE devices; User/Device; bearer on all APIs | UX05/UX10/UX14 | SEC-01/02 | T15/T36 | 1 web, 3 native |
| R16 Privacy/retention/deletion | F16 Privacy | DELETE screenshots/sessions/tasks/account; DeletionJob/EvidenceLink | UX03/UX10 | SEC-04/10/11/13 | T16/T34/T35 | 1 then every phase |
| R17 Scope/risk | F17 App/safety gate | Permission/TaskStep.policy_disposition | UX05/UX08/UX13 | SEC-06/07/08 | T17/T29/T47/A08 | 1/2/4 |
| R18 Injection resistance | F18 Untrusted evidence | Analysis/Instruction schemas; SafetyEvent | UX08 | SEC-09/10/14 | T18/T31/T46/T47/A12 | 1 then every provider change |
| R19 Service boundaries | F19 Backend mediation | Versioned API; Operation; architecture 06 | UX01/UX14 | SEC-01/10/11/15 | T19/T28/T46 | 0/1/3 |
| R20 State integrity | F20 State control | GuideSession/Operation/GuidanceEvent; GET events | UX06/UX07/UX08 | SEC-05/12/13 | T20/T33/T37/T44/T45 | 1 base, 2 full, 4 events |
| R21 Accessibility/geometry | F21 Accessibility | Instruction.pointer; local CaptureGeometry | UX03/UX06/UX12 | SEC-03/15 | T21/T39 | 1 web, 3/4 native |
| R22 Failure safety | F22 Degraded mode | Error envelope; Operation/Permission | UX07/UX08 | SEC-05/12 | T22/T32/T33 | Every phase |
| R23 Cost/abuse/observability | F23 Budgets | Rate profiles; Operation/SafetyEvent | UX08 | SEC-10/13/14 | T23/T38/T42 | 1 then every phase |
| R24 Six MVP categories | F24 Certified tasks | Category enum; TaskStep/verifier profiles | UX02/UX06 | SEC-06/07 | T24/A01/A02 | 1–5, 6a certification |
| R25 Broad domains/narrow release | F25 Expansion | Taxonomy 10; allowlist policy version | UX02/UX08 | SEC-06/07/15 | T25 | 0 catalogue, 6b expansion |
| R26 Future learning handoff | F26 Optional transition | Future purpose-scoped adapter, no MVP endpoint | UX09 future opt-in | SEC-16 | T26 contract fixture | 0 design, future implementation |
| R27 Windows lifecycle | F27 Packaging | Device/client_version; native local gate | UX14 | SEC-02/12/15 | T27/T36/T40 | 3/5 |
| R28 Verification strategy | F28 Testability | OpenAPI/entity schemas/test adapters | UX01–UX14 acceptance | SEC-01–SEC-16 | T01–T48/A01–A13 | All phase gates |
| R29 External/high-risk actions | F29 Specific confirmation | POST action-confirmations; ActionConfirmation | UX13 | SEC-07/08/15 | T29/A08 | 2, expansion remains gated |
| R30 Repository truth/ADRs | F30 Alignment | Inspection report/ADRs; no legacy endpoints found | UX14 truthful capability | SEC-13/15 | T30 | 0 and every contract change |

## Cross-cutting coverage checks

All 30 R IDs have F/API-or-entity/UX/SEC/T/phase mappings. T31–T40 supplement row-specific tests for grounding, timing, crashes, deletion, devices, event streaming, performance, usability and full release flow. T41–T48 cover the Guide Engine v2 mechanisms — tiered admission, the observation route and its budgets, continuous-observation consent and stop, the server-driven guide and its self-report arm, stuck detection and replan, the provider role abstraction, conversation import and completion honesty. A01–A13 are the required acceptance scenarios. Internal roles map through R18/R19/R20/R26, and every taxonomy row inherits one verifier/failure profile in 10 plus SEC-06/07/08. Each ADR states related R IDs and revisit conditions.

No test status is marked passed for an unimplemented product. Before each phase closes, replace planning-only references in a separate implementation status report with code paths and actual test-run artifacts. Keep these requirement IDs stable; adding a requirement adds an ID and all matrix columns. Removing or changing a requirement requires an ADR and migration/compatibility assessment where applicable.

Assumptions: baseline v1 contracts; no source implementation existed at inspection. Dependencies: all numbered documents and ADRs. Open decisions: D01–D07 in README map to release gates in 15, not missing requirement coverage. Example: a PR implementing pause is incomplete if it adds UX07 but omits epoch cancellation and T11 capture-stop evidence. Security considerations are explicit in every row.

Local browser development exception: [ADR-015](adr/015-browser-observation-and-personal-cloud.md) maps R06/R08/R11/R16/R18/R22 to `screenCapture.ts`, `LiveGuide.tsx`, `cloud.py`, capture lifecycle unit tests, `test_cloud.py` and `e2e/live-guide.spec.ts`. Evidence and remaining native/provider limitations are in [19](19-implementation-status.md); this does not mark the broader requirement tests complete.

Guide Engine v2 implementation mapping: the migration in [20](20-guide-engine-migration-plan.md) is merged through PR-18 and maps T41–T48 to code and tests as follows — T41 to `web/src/guide/observer.ts` with `observer.test.ts`; T42 to `app/guide/observation.py` and the `/sessions/{id}/observe` route with `tests/test_observation.py`; T43 to `app/api.py` consent, counter and stop routes, `web/src/guide/watching.ts` and `overlay/frameSource.ts`, with `tests/test_consent.py`, `watching.test.ts` and `e2e/watch-consent.spec.ts`; T44 to `app/guide/engine.py`, `app/guide/steps.py` and `web/src/guide/live.ts`, with `tests/test_self_report.py`, `live.test.ts` and `e2e/guide-island.spec.ts`; T45 to `app/guide/replan.py` with `tests/test_replan.py` and `e2e/replan.spec.ts`; T46 to `app/providers/` with `tests/test_provider_matrix.py` and `tests/test_providers.py`; T47 to `app/imports/` with `tests/test_imports.py` and `e2e/import.spec.ts`; T48 to `app/guide/summary.py` with `tests/test_summary.py` and `e2e/summary.spec.ts`. Run counts and the limits these tests do not cover — no live provider request, no native client, no PostgreSQL concurrency proof — stay in [19](19-implementation-status.md). Rows above are not marked complete by this mapping. PR-20 adds the implemented arm of T10 — `POST /sessions/{id}/feedback` in `app/api.py` with `app/guide/feedback.py`, covered by `tests/test_feedback.py` and `e2e/incorrect-guidance.spec.ts` — and the measuring half of T31: `app/guide/calibration.py` with `scripts/calibration.py`, covered by `tests/test_calibration.py`. T31's held-out evaluation corpus is still absent, so calibration is instrumented rather than done. PR-21 adds T49 in `web/src/overlay/surface.ts` with `surface.test.ts` and `e2e/surfaces.spec.ts`. PR-24 adds the first real provider path for T22 and T31: `scripts/smoke_provider.py` with `tests/test_smoke_script.py` covering its guardrails, and `.github/workflows/provider-smoke.yml` as the manual, credentialed job. PR-22 adds the concurrency arm of T20: `tests/test_concurrency.py`, which runs only against PostgreSQL and skips on SQLite rather than reporting green where the row locks do nothing.
