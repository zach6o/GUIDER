# Architecture decision records

Status: proposed product implementation baseline, 2026-09-07. No ADR implies existing code, provider procurement or deployment approval. Decisions are normative defaults for the requested design; open deployment decisions are D01–D07 in [the documentation README](../README.md).

| ADR | Decision | Requirement trace |
|---|---|---|
| [001](001-standalone-user-mode.md) | Standalone User Mode first | R19/R26/R30 |
| [002](002-screenshot-first.md) | Screenshot-first support | R03/R06/R24 |
| [003](003-opt-in-observation.md) | Opt-in scoped observation | R06/R11/R17 |
| [004](004-no-raw-video-storage.md) | No raw screen-video storage | R16/R23 |
| [005](005-guide-not-control.md) | Guide instead of control | R08/R17/R29 |
| [006](006-floating-windows-overlay.md) | Floating Windows overlay | R07/R12/R21/R27 |
| [007](007-multiple-domains-limited-mvp.md) | Broad domains, limited MVP | R24/R25 |
| [008](008-supabase-auth.md) | Supabase remains identity provider | R15/R19 |
| [009](009-persist-task-state.md) | Persist task/checkpoint state | R13/R14/R20 |
| [010](010-one-step-guidance.md) | One verified step at a time | R08/R09/R10 |
| [011](011-application-allowlisting.md) | Application allowlisting | R17/R24 |
| [012](012-high-risk-action-gates.md) | Block or specifically confirm high risk | R17/R29 |
| [013](013-agent-zero-integration.md) | Future Agent Zero authorization boundary | R19/R26 |
| [014](014-initial-stack-and-contracts.md) | Initial stack and service contracts in empty repository | R15/R19/R20/R30 |
| [015](015-browser-observation-and-personal-cloud.md) | Local browser observation and personal OpenAI connection; accepted development exception | R06/R08/R11/R16/R18/R22 |
| [016](016-web-first-tiered-observation.md) | Web-first guidance with tiered observation | R06/R07/R11/R12/R16/R21/R23 |
| [017](017-provider-role-abstraction.md) | Provider abstraction by bounded role | R18/R19/R22/R23 |
| [018](018-imported-conversation-context.md) | Imported conversation context | R02/R05/R18 |
| [019](019-context-engine.md) | Screen context as a first-class belief | R06/R08/R10/R23 |
| [020](020-overlay-surfaces.md) | Two overlay surfaces, one mark vocabulary | R07/R08/R21 |
| [021](021-managed-provider-mode.md) | Managed credentials as a source, not a second pipeline | R15/R19/R23 |

## v2 supersessions

ADRs 016–018 belong to the Guide Engine architecture in [20](../20-guide-engine-migration-plan.md). They change these earlier decisions and no others.

| ADR | Status |
|---|---|
| [016](016-web-first-tiered-observation.md) | **Adopted** 2026-09-12. Its own gates stay shut: no production continuous observation before the D06 notice and the [011](011-application-allowlisting.md) native gates |
| [017](017-provider-role-abstraction.md) | **Adopted** 2026-09-14. The provider package, registry and role protocols shipped in PR-1; PR-16 added a second adapter and the exit gate that reads `app/` and fails if anything outside `app/providers/` names a provider. D01 remains open per provider for account mode |
| [018](018-imported-conversation-context.md) | **Adopted** 2026-09-14. Implemented in PR-17: paste-only transport, redaction before the row is written, injected instructions dropped, restricted actions kept and blocked, and a draft the user confirms |

## V2 · live visual instruction

ADRs 019–021 belong to the architecture in [22](../22-guider-v2-architecture.md). All three are
**proposed**; nothing in them is implemented, and no phase of that plan begins before its
architecture is approved.

| ADR | Status |
|---|---|
| [019](019-context-engine.md) | Proposed. Adds a second observation role and a derived, content-free record. Load-bearing assumption: a cheap model produces a stable digest |
| [020](020-overlay-surfaces.md) | Proposed. Records that a browser cannot draw on another application's window, and defines one mark vocabulary for both surfaces so the native overlay is a renderer swap |
| [021](021-managed-provider-mode.md) | Proposed. Keeps premium access as a credential source inside the existing registry. Blocked on D01 and D02 |

| Earlier ADR | Status under v2 | What changes |
|---|---|---|
| [002](002-screenshot-first.md) | Amended | Screenshot-only remains a fully supported path and the degradation target; it is no longer the only path before live observation |
| [003](003-opt-in-observation.md) | Superseded in part by [016](016-web-first-tiered-observation.md) | User-triggered stills become locally change-gated admission under separate continuous-observation consent. Default-off, single window, no full display, immediate local stop and fresh permission after resume are preserved |
| [004](004-no-raw-video-storage.md) | Reinforced | Observation frames are never persisted at all, which is stricter than the ≤24 h still retention |
| [006](006-floating-windows-overlay.md) | Deferred by [016](016-web-first-tiered-observation.md) | The MVP guidance surface is a web island with Document Picture-in-Picture; native floating windows remain the target for a separately authorized native client |
| [011](011-application-allowlisting.md) | Unchanged and still open | A browser cannot attest executable identity; the native allowlist stays required before any distributed release, and continuous observation stays unavailable in production until it exists |
| [014](014-initial-stack-and-contracts.md) | Amended by [016](016-web-first-tiered-observation.md)/[017](017-provider-role-abstraction.md) | The WPF client leaves the MVP path and is archived; no Electron or Tauri replaces it. Stack, transport and contract decisions are otherwise unchanged |
| [015](015-browser-observation-and-personal-cloud.md) | Generalized | The loopback BYOK connector becomes one provider adapter rather than the only cloud path |

[005](005-guide-not-control.md), [008](008-supabase-auth.md), [009](009-persist-task-state.md), [010](010-one-step-guidance.md), [012](012-high-risk-action-gates.md) and [013](013-agent-zero-integration.md) are unchanged by v2. Automatic step advancement under [016](016-web-first-tiered-observation.md) is evidence-driven and therefore consistent with [010](010-one-step-guidance.md), which prohibits advancing on a timer, a click or a user's word alone.

Change process: add a superseding ADR for identity, safety, data ownership/retention, session semantics, incompatible API, execution rights, platform integration or service-boundary changes. Update affected specs and [traceability](../17-traceability-matrix.md) in the same change. Minor implementation fixes within these contracts need no new ADR. No blanket permission gate is introduced for routine work.

Each ADR includes context, decision, alternatives, consequences, revisit conditions, assumptions/dependencies/open decisions, security and a local traceability table. Example: adding an automatic terminal executor would supersede 005 and 012, require new explicit product authorization and tests; a checkbox labeled Confirm alone cannot authorize this scope change.
