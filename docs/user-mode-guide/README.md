# Kurukul Guide Mode documentation

Baseline: 2026-09-07 · specification version 1.0 · implementation status: **the [20](20-guide-engine-migration-plan.md) Guide Engine migration is merged in full, phases 0–4**; release gates D01, D05 and D06 and the native client remain open. See [current implementation status](19-implementation-status.md) for code, verification and remaining gates. The repository inspection and implementation-status statements below describe the original pre-code baseline.

“Complete difficult computer tasks with a visual guide, one verified step at a time.”

Guide Mode is a Windows-focused assistant that explains and points while the user performs the work. It is a standalone User Mode product designed to become a Kurukul module. It is not only for coding. User Mode supplies practical help; Learner Mode supplies structured learning; Institutional Mode is outside this release.

The local browser guide is an accepted development exception to the original phase order: [ADR-015](adr/015-browser-observation-and-personal-cloud.md). It adds user-selected window/tab preview and individually reviewed OpenAI frame checks through a temporary personal-key connection. Native observation and production release gates remain open. See [19](19-implementation-status.md) for current evidence and the root [README](../../README.md) for startup instructions.

The screen-guide page defaults to a no-key interactive practice app. Floating target hints, sample action verification, automatic next-step progression and optional playback demonstrate the intended interaction. Local window mirroring can sit behind the practice overlay, including in browser fullscreen. It does not analyze or control the mirrored window. Actual frame-based guidance is available separately through the **OpenAI guide** mode.

## Repository evidence and status vocabulary

Initial inspection found only `.git/`, an unborn `main` branch, no tracked files, no commits and no configured remote. A `.claude/skills/` tooling collection appeared during the task and was inventoried at final inspection; it was not created or modified by this documentation work. There are no existing product applications, APIs, models, authentication integrations, ports or migrations to preserve. See [the inspection report](18-repository-inspection-report.md). No product implementation is included in this documentation change.

| Label | Meaning in this documentation |
|---|---|
| Existing | Directly verified artifact; repository metadata, concurrent `.claude/skills/` tooling and this documentation qualify, not a product implementation |
| Partial | Some supporting implementation exists; none was found |
| Proposed MVP | Normative implementation target, not a claim of working software |
| Post-MVP | Later standalone product expansion, disabled until separately implemented and tested |
| Future | Kurukul platform integration or research; not a release commitment |
| Deprecated | Existing behavior retained during replacement; none was found |

## Reading map and authority

| Document | Purpose and authority |
|---|---|
| [01 Product requirements](01-product-requirements.md) | Scope, requirement IDs, outcomes and exclusions |
| [02 Functional specification](02-functional-specification.md) | User flows and functional acceptance |
| [03 Screenshot and vision](03-screenshot-and-vision.md) | Media limits, coordinates, redaction and evidence |
| [04 Windows client](04-windows-client.md) | Native behavior, capture gates and packaging |
| [05 State machine](05-session-state-machine.md) | Authoritative session states, transitions and recovery |
| [06 Architecture](06-system-architecture.md) | Service boundaries, proposed stack and configuration |
| [07 API contracts](07-api-contracts.md) | Authoritative routes, transport schemas and concurrency |
| [08 Data model](08-data-model.md) | Authoritative persisted entities, enums and retention |
| [09 Security and privacy](09-security-and-privacy.md) | Authoritative safety rules; overrides permissive interpretations |
| [10 Task taxonomy](10-task-taxonomy.md) | Task-specific scope and capability matrix |
| [11 UX](11-ux-specification.md) | Screens, copy, accessibility and interaction |
| [12 Agent responsibilities](12-agent-responsibilities.md) | Internal roles and future Kurukul boundaries |
| [13 AI behavior](13-ai-behavior-policy.md) | Model inputs, outputs and instruction rules |
| [14 Error handling](14-error-handling.md) | Recovery messages, retries and fail-closed behavior |
| [15 Implementation plan](15-mvp-implementation-plan.md) | Dependency order, deliverables and phase gates |
| [16 Testing](16-testing-strategy.md) | Test IDs and measurable release acceptance |
| [17 Traceability](17-traceability-matrix.md) | Requirement → behavior → contract → UX → security → test → phase |
| [18 Inspection report](18-repository-inspection-report.md) | Repository facts and evidence limitations |
| [19 Implementation status](19-implementation-status.md) | Implemented scope, verification evidence and remaining phase gates |
| [20 Guide Engine migration plan](20-guide-engine-migration-plan.md) | Approved v2 migration, invariants and PR-sized phases; all phases merged through PR-18 |
| [21 Observation consent notice](21-observation-consent-notice.md) | Normative wording for continuous-observation consent; **draft pending D06** |
| [ADRs](adr/README.md) | Decision rationale and change controls |

Resolve conflicts by domain authority above. Do not silently choose between conflicting contracts: fix the documents and associated traceability first. `MUST`, `MUST NOT` and `SHOULD` are normative requirements, prohibitions and defaults with documented exceptions. ADRs explain decisions but do not override newer explicit contracts without updating both.

## MVP and deliberate exclusions

MVP phases 1–5 implement screenshot help, editable plans, a Windows overlay, opt-in observation, verification, voice and recovery. Supported workflow categories are `setup`, `run`, `debug`, `understand`, `test`, `git_github`. Initial applications: VS Code, PowerShell/Windows Terminal, Chrome/Edge, Git/GitHub, Python, JavaScript/TypeScript and basic Docker Desktop. Phase 6 first certifies these workflows, then adds separately scoped Office and creative support after MVP.

No mouse/keyboard injection, shell execution, filesystem modification, background monitoring, raw screen-video storage, automatic communications, arbitrary enterprise integration or banking/payment/medical/legal/government workflows. Explicit confirmation permits **guidance for a user-performed action**, never autonomous execution in MVP. A blocked action cannot be unlocked with confirmation.

Canonical loop: understand → plan → confirm → optionally permit observation → one instruction → user action → evidence → verification → next instruction or revision. Screen permission, action confirmation and verification are separate records.

## Implementation defaults and unresolved decisions

All values are proposed product defaults, not discovered deployment settings. Adopt them for implementation unless changed through the identified decision process.

| ID | Decision still needed | Working default / dependency / resolution owner |
|---|---|---|
| D01 | Vision/LLM and speech provider, model versions, region, retention contract and budgets | Adapter interfaces and test doubles first. No production media transmission until provider review; engineering + privacy owner before phase 1 pilot; speech review before phase 5 |
| D02 | Hosting, Supabase project, managed PostgreSQL, object storage, KMS and backup region | Architecture defines portable boundaries; no cloud vendor provisioned. Platform owner before deployed phase 1 |
| D03 | Windows 10 servicing eligibility and release support window; ARM64 demand | Windows 11 x64 primary; Windows 10 22H2 x64 compatibility target subject to security servicing gate. Windows owner before phase 3 pilot |
| D04 | Signing identity, installer distribution and update feed | Signed MSIX, user-scoped install, explicit updates while idle. Release owner before distributing phase 3 |
| D05 | Performance/cost budgets and pilot dataset calibration | Targets in 01 and 16 are hypotheses; product + engineering validate before MVP launch |
| D06 | Provider/backup erasure terms, retention notice, age eligibility and operating regions | Proposed product retention in 08; privacy owner validates notice and supplier commitments before production |
| D07 | Accessibility certification, app versions/locales and release hardware matrix | English UI/voice, x64, 1080p+ test baseline; accessibility + QA owner before MVP launch; smaller screens still functional |

Unresolved items are deployment/pilot gates, not excuses to improvise APIs. No unresolved choice authorizes a second identity provider, automatic control or continuous observation. The selected stack is documented in ADR-014 and may be revised before scaffolding with an ADR.

## How a coding agent should work

1. Read 18, this README, 01 and the ADRs. Confirm that repository evidence is still current.
2. Read 05, 07, 08 and 09 together. Implement one vertical phase from 15 using tests in 16 and coverage in 17.
3. Treat every service and UI route as proposed until code and tests prove it exists. Keep `user-mode/web`, `user-mode/backend` and `user-mode/client/windows` independently buildable.
4. Convert the contract in 07 to checked-in OpenAPI/JSON Schema in phase 0/1; keep entity enums and examples synchronized. Do not implement later phases early.
5. Resolve phase-specific decisions before shipping that phase. Use fixtures without real customer media while provider/deployment decisions remain open.
6. Update documents, ADRs, tests and traceability in the same change when a contract changes. Never delete a discovered legacy feature silently.

Example: “I cannot run Python” → upload a cropped terminal screenshot → review the plan → “In the VS Code terminal, type `python --version`; tell me what appears.” A later screenshot proves the interpreter is available; saying “done” alone does not.

Shared assumptions: authenticated individual users, an interactive Windows desktop, outbound HTTPS, user-performed work and no local-file access beyond explicit image/audio selection. Dependencies and security rules are linked by every document's implementation notes; [17](17-traceability-matrix.md) is the master traceability matrix.
