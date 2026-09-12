# 16 · Testing strategy

Status: proposed tests and release gates, **no tests have been implemented or executed for a product**. This documentation change is checked for coverage/link/contract consistency only. Use synthetic/redacted fixtures and isolated Supabase/PostgreSQL/storage environments; never real customer screenshots in CI.

## Layers and acceptance IDs

| ID | Test scope | Required assertion / failure injection |
|---|---|---|
| T01 | Homepage and auth gating | Three primary actions; local draft/media not uploaded before sign-in; keyboard journey works |
| T02 | Task creation | Goal/category/app validation, ownership-derived ID, atomic initial session, duplicate key returns one task |
| T03 | Screenshot intake/analysis | PNG/JPEG/WebP limits/signatures, decoder bomb rejection, crop/opaque redaction precede upload, explanation/boxes bound to evidence |
| T04 | Media lifecycle and voice intake | Replace invalidates old work; delete removes bytes/derivatives; clip codec/duration limits; transcript review required; mic canceled on stop |
| T05 | Plan confirmation | Edits create new version; stale approval/start rejected; exact confirmed plan used; unsafe/risk changes cannot bypass reapproval |
| T06 | Permission flow | Off by default; denial still permits manual screenshots; backend request cannot grant OS permission; fresh local grant for app/scope change; observed upload requires single-use unexpired CaptureIntent |
| T07 | Overlay visibility/position | Dot draggable/clamped; pointer click-through; native cursor untouched; readable card; stopped overlay gone |
| T08 | One instruction | Current instruction anatomy and one action; explanation/repeat does not advance; screen-reader labels present |
| T09 | Verification | Done creates claim only; objective evidence required for passed; inconclusive/self-report not achieved; stale/deleted evidence rejected |
| T10 | Incorrect guidance/recheck | New image after mismatch cancels obsolete result; incorrect report blocks and removes marker; revision limit enforced |
| T11 | Pause | Local capture gate closes p95≤100ms, max250ms; no post-gate acquired/uploaded frame; queued images dropped; manual upload remains paused |
| T12 | Stop/close/emergency | All overlays/mic/capture removed locally without network; late result cannot redisplay; backend terminal stopped summary consistent |
| T13 | Resume/history/restart | Paused checkpoint recovered; terminal creates successor; no old grant, frame or pointer reused; image expiry visible |
| T14 | Summary/feedback | Outcomes achieved/user_reported/stopped/failure honest; private feedback saved; summary fallback works without LLM |
| T15 | Auth/authorization | Invalid signature/issuer/audience/expiry/kid, foreign IDs, cross-task references, revoked user/device and missing bearer rejected; JWKS rollover tested |
| T16 | Privacy/deletion | Screenshot/audio/task TTL exact access cutoff; no payload in logs; account deletion stops sessions, purges objects/context, handles backups/receipts |
| T17 | Allowlist/sensitive screen | Wrong executable/publisher, browser banking tab, password field, UAC/lock screen blocked before capture/upload; uncertainty → manual fallback |
| T18 | Prompt injection and output | Screenshot/web/code malicious instructions cannot grant tools/consent; unsafe HTML/links rejected; malformed/out-of-range boxes rejected |
| T19 | Architecture boundaries | Web/native have no model/service keys or direct Guide DB access; internal roles only Orchestrator-dispatched; independent builds/config |
| T20 | State machine/concurrency | Exercise every transition in 05 and representative forbidden transitions; compare-and-swap, priority stop, epoch races and atomic outbox |
| T21 | Accessibility/DPI/monitors | Narrator/keyboard/high contrast/200% text; 100–250% DPI, negative origins, portrait, unplug/primary switch; no focus theft |
| T22 | Network/provider/voice failures | Disconnect in each media stage; expired JWT mid-capture; LLM timeout/malformed result; voice failure creates no command |
| T23 | Quotas/abuse | Per-user/device/IP budget/concurrency; Retry-After; 40-call budget; pause/stop/revoke work when ordinary quota exhausted |
| T24 | Six MVP categories/app packs | At least 5 reproducible tasks/category across named apps; controlled package/framework versions; no claim of arbitrary app support |
| T25 | Expansion boundaries | P/F taxonomy rows disabled/clearly labeled; unsupported domains cannot silently enable live observation or new v1 enum |
| T26 | Future integration contract | Contract fixture proves minimum consented handoff; Agent Zero unavailable/denied leaves basic Guide independent; no production integration claimed |
| T27 | Packaging/startup/update | Signed MSIX identity, user-scoped install/uninstall, no autostart monitoring, update idle-only, invalid signature/downgrade rejected |
| T28 | API schema/contracts | Generated OpenAPI examples validate; auth/error/idempotency/rate/audit profiles on every route; clients deserialize same enums/nullability |
| T29 | Risk confirmation | Blocked tasks cannot be confirmed; medium/high allowed guidance needs target/version-bound challenge; changed target/expired/voice approval rejected; confirmation publishes exactly the reserved pending instruction and consumes challenge once |
| T30 | Repository/documentation alignment | Inspection matches actual tree; no undocumented routes/models/envs; contract changes accompanied by ADR and traceability |
| T31 | Vision grounding/evaluation | Gold boxes/labels, ambiguous controls, low-resolution/wrong-language fixtures; confidence calibration; false passes ≤2% target on held-out set |
| T32 | Expiry/permission/recovery | 30min idle, paused idle exception, 24h hard session expiry, 15min grant/15s lease, heartbeats do not extend activity or permission |
| T33 | Crash/backend restart | Kill client during capture, worker during provider call, API after DB commit; no independent capture survives, no duplicated steps/events, no auto-resume |
| T34 | Storage/retention robustness | Fake clock TTL, online purge ≤24h, media excluded from backup, restore replays erasure ledger, failed purge alerts and stays unreadable |
| T35 | User deletion race | Concurrent upload/provider/result/SSE/read/idempotency replay versus deletion: tombstone wins, no orphan accessible bytes, identity removed after purge |
| T36 | Native login/device control | PKCE code/state/replay/callback mismatch; DPAPI/credential storage; device credential+JWT; controller transfer rejects old device/epoch |
| T37 | Event stream security | Header bearer auth, expiry/revoke closure, replay order/dedup/gaps, cursor owner isolation, no content/tokens in event URL/payload |
| T38 | Performance and cost | Declared network/hardware: first explanation p95≤15s, recheck p95≤10s; user wait and provider cost measured separately; no busy capture loop |
| T39 | Usability | Pilot tests instruction clarity, cannot-find recovery, privacy comprehension, task completion; no unreadable idle fade or hidden stop |
| T40 | Full Windows release flow | Signed fresh install → login → Python/VS Code/manual+live+voice → pause/revoke/network/restart → complete → delete → uninstall; evidence report per OS/app build |

Unit tests: policy dispositions, state reducers, schema validators, coordinate transforms, retention cutoff and budgets. Integration: real PostgreSQL transactions/constraints, private object store abstraction, Supabase validation fixture/mock JWKS plus isolated live Auth test. Contract: generated OpenAPI/JSON schemas and captured sanitized examples. End-to-end: web browser flow and native UI Automation/manual QA; provider nondeterminism evaluated separately with labeled fixtures. Do not use SQLite to claim PostgreSQL transaction/security behavior is validated.

## Required end-to-end acceptance scenarios

| Scenario | Given / When | Then / evidence to retain | Test IDs |
|---|---|---|---|
| A01 Python screenshot explanation | Signed-in user uploads cropped Python import error and asks why | Redacted image only uploaded; explanation grounded in visible error; box overlays correct viewer region; no desktop pointer/capture | T03/T15/T31 |
| A02 VS Code setup | User describes setup goal, reviews/edits/confirms plan and starts | Exactly one readable instruction; Done alone does not advance verified progress; user can ask why/cannot-find | T02/T05/T08/T09 |
| A03 Pause stops capture | Approved window grant and a recheck queued; user presses Pause | Gate timestamp precedes any later frame admission; queue cleared, upload canceled, epoch invalidates late result; manual screenshot can be shared while paused | T11/T20/T32 |
| A04 Stop removes overlay | Active dot/card/pointer; user chooses Stop with network disconnected | All owned overlays/mic/capture disappear within local safety deadline; normal desktop works; later backend marks stopped without reappearance | T07/T12/T22 |
| A05 Denied permission/manual mode | User denies native picker/consent | Clear screenshot-only option, no capture frame/socket/media data from desktop; uploaded manual evidence can complete task | T06/T17 |
| A06 New screenshot after failure | Current instruction mismatches; user submits new screenshot | Old pointer/operation invalidated; new evidence drives revised current instruction; no false success | T04/T10/T20 |
| A07 Resume paused task | Task paused and client restarted | History shows checkpoint; review and resume in screenshot-only or new consent; old permission never reused | T13/T32/T33 |
| A08 Blocked high risk | User asks to operate banking/payment or security-sensitive account screen, then says “I confirm” | Block persists, no actionable pointer/instruction/capture; content-free SafetyEvent; safe exit offered | T17/T29 |
| A09 Voice next step | User explicitly records “What is the next step?”, reviews transcript and sends | Ordinary command created; current unverified step remains current; voice cannot bypass verification/confirmation; clip purged | T04/T08/T09/T22 |
| A10 Task completion | Fresh evidence passes last required criterion | Completed achieved summary lists verified steps and next action; capture/grants/overlays off; history private; self-report-only variant labeled user_reported | T09/T12/T14/T16 |

These scenarios must run against production-like contracts and the real native capture boundary, not just mocked UI buttons. A03/A04 require instrumented capture/upload timestamps and network sink records with synthetic images; a screenshot showing a paused label alone is insufficient proof that capture stopped.

## Fixture and hardware matrix

At least: Windows 11 x64 release build selected under D03, Windows 10 22H2 x64 on approved servicing path before any compatibility claim; 1/2/3 monitors, left/top negative coordinates, mixed DPI, portrait, docking/unplug, locked desktop, sleep/resume, minimized/occluded/straddled target, UAC, protected content and shortcut conflicts. Use 1080p and 4K plus small work-area/text-zoom stress. Enumerate exact OS/app/client/provider versions in report, not just “Windows passed.” ARM64/RDP are unsupported until separate tests.

Provider evaluation corpus: ≥100 redacted synthetic tasks with held-out failures/ambiguous UI; ≥200 labeled verification decisions to estimate false-pass target without treating model confidence as accuracy. Report confidence intervals/sample size and domain breakdown; pilot thresholds in 01 are hypotheses. Repeat provider evaluation after model/prompt/app version changes. No provider request in ordinary unit CI; opt-in integration job uses approved credentials and budget.

## Release evidence and decisions

Evidence artifact: test ID, contract/commit version, OS/app/provider versions, fixture IDs, expected/actual state, sanitized trace IDs, pass/fail, reviewer and unresolved issues. Privacy logs contain no raw media. Safety-critical T06/T11/T12/T15/T16/T17/T20/T29/T32–T37 must all pass; no launch with known unauthorized capture, cross-owner disclosure or false deletion. D01–D07 unresolved gates require explicit resolution before corresponding release, not blanket coding blockage. Traceability: [17](17-traceability-matrix.md). SEC-01–SEC-16 covered by tests above.
