# 20 · Guide Engine migration plan

Status: **proposed, awaiting approval**. No code change is authorized by this document. It records how the implemented slice in [19](19-implementation-status.md) becomes the Guide Engine architecture, which decisions change ([ADR-016](adr/016-web-first-tiered-observation.md)/[017](adr/017-provider-role-abstraction.md)/[018](adr/018-imported-conversation-context.md)), and the order of work. Authority for states stays with [05](05-session-state-machine.md), for routes with [07](07-api-contracts.md), for entities with [08](08-data-model.md) and for safety with [09](09-security-and-privacy.md); this plan adds to them and overrides none.

## Invariants

These hold in every phase below. A change that breaks one is out of scope and requires its own ADR.

1. No rewrite. Existing modules are refactored or extended, never replaced wholesale.
2. The security model is preserved: Supabase-only identity, owner-scoped composite foreign keys, `state_version`, `control_epoch`, idempotency receipts, the deletion cascade and the deterministic Safety Guard.
3. The data model is preserved: additive migrations only. No column is dropped, renamed or retyped.
4. Web-first. No Electron, Tauri, WPF or other native dependency is added.
5. Guider guides. No mouse, keyboard, shell, filesystem or application automation, per [ADR-005](adr/005-guide-not-control.md).
6. LLMs reason; the Guide Engine owns state. A provider result is a proposal until schema, authorization, epoch and guard checks pass. Only the engine writes session and step state.
7. No continuous raw screenshot streaming. Observation uses the tiered model in [ADR-016](adr/016-web-first-tiered-observation.md).

## Specification review

Most of the v2 architecture is already specified and unimplemented. The `SessionState` enum in the running code already contains `plan_ready`, `instruction_ready`, `awaiting_user_action` and `verifying`; `guide_sessions` already carries `current_step_id` and `confirmed_plan_version`; [08](08-data-model.md) already defines `TaskPlan`, `TaskStep`, `Instruction`, `CompletionClaim`, `VerificationResult` and `SessionSummary` to the column; [12](12-agent-responsibilities.md) already names the roles. The work is to build the unbuilt half of this specification, not to redesign it.

| Document | Action | When |
|---|---|---|
| [03](03-screenshot-and-vision.md) | Add the tiered observer, admission thresholds and the never-persisted rule for `source=observation` | Phase 3 |
| [04](04-windows-client.md) | Mark the native client deferred; point at [ADR-016](adr/016-web-first-tiered-observation.md) | Phase 0 |
| [05](05-session-state-machine.md) | Add observer ticks as the `awaiting_user_action` self-transition, the confidence bands and the replan reason. No new state | Phase 2 |
| [06](06-system-architecture.md) | Add `app/guide/`, `app/providers/`, `app/imports/` and the synchronous observation path | Phase 0 |
| [07](07-api-contracts.md) | Add the sixteen v2 routes; record `/observe` as the sole idempotency exception | Phase 1–4 |
| [08](08-data-model.md) | Add `provider_connections`, `imported_conversations`; add the step and session columns below | Phase 1 |
| [09](09-security-and-privacy.md) | Continuous-observation consent, frame counter, notice version bump | Phase 3 |
| [11](11-ux-specification.md) | Guide island states, plan review screen, provenance for imported plans | Phase 2 |
| [12](12-agent-responsibilities.md) | Add Observer and Replanner to the responsibility map | Phase 0 |
| [15](15-mvp-implementation-plan.md) | Cross-reference this plan; original phases 3–5 are re-sequenced, not deleted | Phase 0 |
| [16](16-testing-strategy.md)/[17](17-traceability-matrix.md) | New test IDs and trace rows per phase | Every phase |

## Architecture delta

| Concern | Today | After migration |
|---|---|---|
| Progression | A reducer in `web/src/demoGuide.ts`, frontend only | `app/guide/engine.py` is the sole writer; `web/src/guide/engine.ts` is an optimistic mirror sharing the demo's test coverage |
| Intelligence | `FixtureProvider` on the account path, `OpenAIVision` inline on the local path | `app/providers/` registry selected by role and capability ([ADR-017](adr/017-provider-role-abstraction.md)) |
| Guard | Regex backstop inside `app/cloud.py` | `app/guide/guard.py`, applied to every role result and to imported text |
| Evidence | User presses a button per still | Tiered admission ([ADR-016](adr/016-web-first-tiered-observation.md)); manual stills remain the fallback |
| Surface | Page sections in `LiveGuide.tsx` | Guide island, Document Picture-in-Picture with two fallbacks |
| Durability of live guidance | None; in-memory connection only | Plans, steps, instructions, claims and verifications persisted under the existing owner scope |

Observation takes a **synchronous** request path with a per-session semaphore, because its latency budget is about one second and a lost tick is covered by the next one. Plan, instruction, verification and replan remain durable leased `Operation` rows. Only the observation *outcome* is persisted, as a `GuidanceEvent`.

## State machine mapping

No new session state is added. The enum is persisted, exported in the OpenAPI contract and referenced by five documents; churn there costs more than it buys.

| v2 behaviour | Existing vocabulary |
|---|---|
| Continuous observation, nothing changed | `awaiting_user_action` self-transition; observer ticks emit events only |
| Observer reports completion | `awaiting_user_action → verifying` on accepted new evidence |
| Automatic advance | `verifying → active → processing → instruction_ready → awaiting_user_action` |
| Replan after anomaly or stuck | `analyzing` with reason `replan`; returns to checkpoint, or to `plan_ready → awaiting_user_confirmation` on a material change |
| Stuck detected | `session.stuck_detected` event; no state change |

[05](05-session-state-machine.md) states that `awaiting_user_action` has no automatic advancement. That prohibits advancing on a timer, a click or the user's word; the same transition table already admits `awaiting_user_action → verifying` on accepted new evidence, and an observed frame is such evidence. Automatic advancement is therefore permitted **only** when backed by a fresh observed frame: confidence ≥ 0.85 advances, 0.60–0.85 asks once with a single tap, below 0.60 shows nothing. Two consecutive mismatches revise the step; the third blocks, which is the existing cap.

New columns, all nullable or defaulted: `guide_sessions` gains `observation_active`, `observation_started_at`, `frames_observed`, `observation_calls`, `reasoning_calls`, `stuck_since`; `task_steps` gains `expected_result`, `fallback`, `explanation`; `verification_results` gains `observed_confidence`; `operations` widens `kind` and gains the `lease_owner`/`lease_expires_at` pair [08](08-data-model.md) already specifies. `expected_result` and `success_criterion` are deliberately distinct: the first is prose shown to the user, the second is the testable condition given to the observer.

## Migration rules

1. Additive migrations only; every revision is reversible by dropping what it added.
2. `FixtureProvider` survives, registers as provider `fixture` and implements every role. Phases 0–2 ship with zero provider spend, as [12](12-agent-responsibilities.md) requires.
3. `/api/v1/local-guide` stays live and unchanged until the session-backed path passes its browser suite, then is re-pointed at the provider registry and kept as the loopback BYOK transport. The current demo never breaks.
4. Feature flags in `Settings`, off by default: `GUIDE_FEATURES=plan,observe,overlay`.
5. `Settings.check()` stays shut and gains new production gates: observation retention, per-provider review, budget enforcement.
6. Contracts regenerate per change through `scripts/export_contract.py`, with CI proving `openapi.json` is not stale.
7. `user-mode/client/windows` moves to `user-mode/client/windows-archive/` with a README recording [ADR-016](adr/016-web-first-tiered-observation.md). It is not deleted.
8. PostgreSQL enters CI with the engine. `SELECT … FOR UPDATE` is a no-op on SQLite, and step progression depends on it.

## Phases

Each item is one pull request. Exit gates are additions to [16](16-testing-strategy.md); no phase starts before its predecessor's gate passes.

### Phase 0 · Foundation — no behaviour change

| PR | Work | Exit gate |
|---|---|---|
| 0 | Commit the working tree; CI runs pytest, ruff, vitest, `tsc -b`, `alembic check` and contract freshness | Green pipeline on a pushed branch |
| 1 | `app/providers/`: Protocols, capability descriptors, registry, schema normalizer. `OpenAIVision` and `FixtureProvider` move behind them unchanged | The existing 39 backend tests pass untouched |
| 2 | `app/guide/guard.py` extracted from `app/cloud.py`, applied to every role result | The blocked-disposition regression test passes for all roles |
| 3 | Documentation: [04](04-windows-client.md), [06](06-system-architecture.md), [12](12-agent-responsibilities.md), [15](15-mvp-implementation-plan.md) updated; ADRs 016–018 adopted | Traceability matrix updated in the same change |

### Phase 1 · Plans and steps — no observation

| PR | Work | Exit gate |
|---|---|---|
| 4 | Migrations and models for `task_plans` and `task_steps` with composite owner foreign keys, joined to the deletion cascade | `alembic upgrade` and `check` clean; cascade test covers plan deletion |
| 5 | Planner role; `POST /tasks/{id}/plans`, `GET /plans/{id}`, `POST /plans/{id}/confirm`; worker gains `kind=plan`; fixture planner returns a deterministic plan | Plan created, confirmed and version-bound; stale confirmation returns 409 |
| 6 | Plan review screen; the user approves the roadmap before anything starts | Browser scenario: create → review → confirm |

### Phase 2 · Guide Engine with manual advance — the product works end to end

| PR | Work | Exit gate |
|---|---|---|
| 7 | `app/guide/engine.py` as sole writer; the [05](05-session-state-machine.md) table enforced with 409 on unlisted transitions; PostgreSQL joins CI | Transition table covered test by test; concurrent claim race tested on PostgreSQL |
| 8 | Instruction role; `GET /sessions/{id}/instruction`; claim and skip routes | Claim recorded separately from verification, per [ADR-010](adr/010-one-step-guidance.md) |
| 9 | `web/src/guide/engine.ts` extracted from `demoGuide.ts`; the practice demo re-pointed at it | All six existing interactive-demo scenarios pass against the shared engine |
| 10 | Guide island: six states, Document Picture-in-Picture with both fallbacks, manual advance only | Keyboard-only run of a full guide; reduced-motion and screen-reader passes |
| 11 | Long-poll `GET /sessions/{id}/events?after=` over `GuidanceEvent.sequence` | Client resumes exactly at its last sequence after a forced reconnect |

### Phase 3 · Observation — requires ADR-016 adopted and the consent notice approved

| PR | Work | Exit gate |
|---|---|---|
| 12 | `web/src/guide/observer.ts`: T0 motion gate and T1 admission, unit-tested against synthetic frame sequences, no network | A static screen admits 0 frames/minute; a scripted UI change admits exactly 1 |
| 13 | `POST /sessions/{id}/observe`, observer role, per-session semaphore, budgets, confidence bands | A 10-minute simulated session stays under 90 observation calls; exhaustion falls back to manual checking |
| 14 | Continuous-observation consent, live frame counter, one-tap stop incrementing `control_epoch` | Stop revokes in-flight work; counter matches server-side count |
| 14b | The island runs a server session: start, the published instruction, claim, self-report, skip and the event stream. `POST /sessions/{id}/steps/{step_id}/verifications`, self-report arm only | A whole plan is guided from the server with nothing marked verified; the island renders the engine's instruction, not the plan text |
| 14c | The consent surface: notice, window choice, mask-once, the tier-2 send loop, the server's frame counter and one-tap stop | Nothing is sent before the notice is accepted and a window chosen; hidden areas are painted out before encoding; running out keeps the guide working |
| 15 | Stuck detection and the replanner; `POST /sessions/{id}/replan` regenerating remaining steps only. Doc 05 gains the `awaiting_user_action → analyzing` row; the replacement is a draft the user confirms | Anomaly injection replans without touching verified steps |

### Phase 4 · Breadth — proving the abstractions

| PR | Work | Exit gate |
|---|---|---|
| 16 | Anthropic adapter plus a provider matrix test running identical fixtures through every adapter. The BYOK connection records which provider it belongs to; `Settings` becomes provider-neutral | Zero provider-specific branches outside `app/providers/`, enforced by a test that reads the source |
| 17 | Conversation import, paste-first, guarded, producing a draft plan ([ADR-018](adr/018-imported-conversation-context.md)). `imported_conversations`, secrets redacted at import, provenance shown on the plan | An instruction injected inside a pasted transcript is caught by the guard; a restricted action is shown and blocked rather than dropped |
| 18 | Session summary and completed-guide history | Verified and self-reported steps are visibly distinguished |

## Risks and open decisions

| Item | Why it matters | Needed by |
|---|---|---|
| False-positive advancement | The principal failure mode. Advancing past a step the user has not done is worse than asking. Instrument mismatch rate from PR 13 and calibrate the 0.85 threshold against real sessions (D05) | Phase 3 |
| Observation cost ceiling | Continuous observation has a real per-hour cost; a daily per-owner ceiling in account mode is a product decision | Phase 3 |
| D01 per provider | Now a per-provider gate ([ADR-017](adr/017-provider-role-abstraction.md)). Blocks account mode; does not block BYOK | Phase 4 |
| Picture-in-Picture absence | Unavailable on Safari and Firefox; fallbacks must be built and tested as first-class, not discovered late | Phase 2 |
| PostgreSQL concurrency | Today's row locks are no-ops on SQLite and the engine depends on them | Phase 2 |
| Continuous-observation notice | Materially different consent from uploading a screenshot; needs D06 approval and a `privacy_notice_version` bump | Phase 3 |
| Allowlisting remains open | A browser cannot enforce [ADR-011](adr/011-application-allowlisting.md); continuous observation stays unavailable in production until native gates exist | Before any release |

## Traceability

R02/R05/R06/R07/R08/R09/R10/R11/R12/R16/R18/R19/R20/R21/R23 → the phase gates above → SEC-01/03/04/05/07/09/10/11/12/13/14. New test IDs are allocated per phase in [16](16-testing-strategy.md) and mapped in [17](17-traceability-matrix.md) in the same change. Current implemented evidence stays recorded in [19](19-implementation-status.md).
