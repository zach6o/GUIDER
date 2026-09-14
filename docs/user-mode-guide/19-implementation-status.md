# 19 · Implementation status and session handoff

## The record catches up with the code: 2026-09-14

No behaviour changed here. The migration in [20](20-guide-engine-migration-plan.md) is merged
through PR-18 — every phase, including the phase-4 exit gate — and three pieces of the record were
still describing an earlier repository.

[ADR-017](adr/017-provider-role-abstraction.md) and [ADR-018](adr/018-imported-conversation-context.md)
are **adopted**. Both were implemented and gate-tested while still marked proposed, which is the
state doc 20's change process exists to prevent. ADR-016's own gates are unaffected and stay shut.

[16](16-testing-strategy.md) gained T41–T48 and A11–A13 for the Phase 3 and 4 mechanisms that had no
test IDs: tiered admission, the observation route and its budgets, continuous-observation consent
and one-tap stop, the server-driven guide and its self-report arm, stuck detection and replan, the
provider role abstraction, conversation import, and completion honesty. Its status line no longer
says no test has been implemented, because that stopped being true at PR-1; it now separates the
proposed release gates from what actually runs in CI. T43 joins the safety-critical set.
[17](17-traceability-matrix.md) maps the new IDs onto the requirement rows they serve and records
which file and which test carries each one.

What is still not proven is unchanged and worth restating in one place: no request in the suite
reaches a provider, the observation loop has never run against a live session, the per-owner row
lock is covered by exactly one concurrent-confirmation test on PostgreSQL in CI and by nothing
under load, there is no native client and therefore no
[011](adr/011-application-allowlisting.md) allowlist, and D01, D05 and D06 remain open. Continuous
observation stays unavailable in production until the last two of those close.

Verification: documentation only. No source file changed, so the counts below still stand.

## Session summary and completed-guide history: 2026-09-13

A task can now end, and the record says honestly how it ended.

`POST /sessions/{id}/completion` takes `achieved` or `user_reported`. `achieved` is a claim about
evidence, so the engine checks it: every required step must be `verified`, and a session resting on
the user's own word is refused with `verification_required` and offered the outcome that is true
instead. `user_reported` needs every required step dealt with — verified, self-reported or
explicitly skipped — and none of them blocked, because a step Guider refused to instruct is not
something a user can report their way past. `GET /sessions/{id}/summary` reads it back; stopping a
task writes one too, so history is never blank (doc 02 F12).

`app/guide/summary.py` builds the summary deterministically from the records rather than asking a
model, and keeps the distinction in its shape: `verified_steps` and `unverified_steps` are separate
columns, and the prose says which is which — "1 was checked on screen. 2 you told Guider were done;
nothing checked those." Skipped, blocked and never-started steps are named in `corrections` rather
than folded into a count.

The island offers "Finish this task" only once the plan has run out, and the web summary screen
shows each step with its own label: checked on screen, you reported this, needs separate review, or
not started. Finished tasks open their summary from history. The browser demo builds the same
summary from the same records, and refuses `achieved` the same way.

Phase 4 of [20](20-guide-engine-migration-plan.md) is complete.

Current verification: 308 backend tests pass and 2 skip on SQLite, 105 web unit tests pass, and 41
browser scenarios pass in installed Chrome.

## Importing a conversation: 2026-09-13

`POST /imports/conversations` takes a pasted transcript and produces a draft plan. Paste is the
only transport, as ADR-018 requires: no extension, no connector, no third-party credential. The
route redacts recognized secrets before the row is written, stores the transcript once for
provenance under retention class H, creates a task and session, and queues an Operation of the new
kind `import`. The worker asks the `import` role, vets the result, and publishes a draft the user
confirms exactly like a generated plan. An import confirms nothing, starts nothing, switches nothing
on.

Pasted text is data. `app/imports/text.py` holds the injection check for this surface: a line that
addresses Guider — "ignore previous instructions", a fake `SYSTEM:` turn, "you are now" — is skipped
when the goal is read and dropped when it appears as a step, because there is nothing in such a step
for a user to review. A *restricted action* is treated differently on purpose: it is kept and marked
`block` by `step_policy`, so the user sees that the conversation suggested `sudo rm -rf` and that
Guider will not walk them through it.

The fixture importer is a parser, not a reader: numbered and bulleted lines become steps with the
same words, the user's own opening line becomes the goal, and the plan says so in its assumptions.
The Anthropic adapter serves the same role for a configured provider, with the transcript marked as
untrusted in its brief.

`app/imports/redact.py` drops provider keys, bearer tokens, labelled credentials, private key blocks
and connection strings carrying inline passwords, and the count is shown to the user. It is a net,
not a guarantee — the 32 KiB cap and the 30-day retention are what limit the rest.

The provider gate from PR-16 was narrowed while doing this: it now forbids adapter classes, adapter
modules and model names outside `app/providers/` — dispatch — and allows a vendor name only in
`app/imports/`, or on a line declaring the import's `source`. That is provenance the user chose,
not a branch on who answered.

Current verification: 291 backend tests pass and 2 skip on SQLite, 99 web unit tests pass, and 37
browser scenarios pass in installed Chrome.

## A second provider, and the gate that proves the abstraction: 2026-09-13

`app/providers/anthropic.py` serves the `guide`, `observe`, `plan` and `instruct` roles against the
Anthropic Messages API: `x-api-key` with `anthropic-version`, the frame as a base64 image block,
and `output_config.format` carrying the same internal schema every other adapter is rendered from.
`schema.py` gained the `native` dialect for it, which closes the schema to undeclared keys rather
than passing a separate strict flag. Raw httpx, like the OpenAI adapter: the suite drives both by
injecting a transport, the dependency set is locked, and one adapter written a different way would
split how the two are tested. No request in the suite leaves the machine.

Models offered are `claude-opus-5` (the default), `claude-sonnet-5` and `claude-haiku-4-5`. A
refusal (`stop_reason: "refusal"`) and a truncated answer (`max_tokens`) are each reported as what
they are; neither becomes a verdict.

Proving ADR-017 turned out to mean fixing three leaks the gate test found. `app/cloud.py` imported
the OpenAI adapter and defaulted its model to an OpenAI name; a connection now records *which*
provider it belongs to and the registry builds the adapter per call, with the model validated by
that adapter's capability descriptor. `Settings` gained `provider_id` / `provider_api_key` /
`provider_model` rather than anything provider-named, and the registry is built per app from those
settings instead of read at import time. The fixture is still registered first, so with no
credentials every role resolves to it and reaches no network.

The local guide screen now asks which service a personal key belongs to, and shows what the backend
said it connected to rather than what was picked in the form.

`tests/test_provider_matrix.py` runs identical fixtures through every adapter serving a role and
holds each answer to the same schema and the same guard, then reads `app/**.py` and fails if
anything outside `app/providers/` names a provider at all. That last test is the phase-4 exit gate,
written as a test rather than a claim.

Not proven: no real Anthropic request has been made. Every answer in the suite is a recorded shape
replayed through an injected transport, and account-mode provider access stays a development switch
until D01 selects a provider.

Current verification: 266 backend tests pass and 2 skip on SQLite, 94 web unit tests pass, and 32
browser scenarios pass in installed Chrome.

## Stuck detection and the replanner: 2026-09-13

A guide can now say that it is going nowhere, and offer a different plan for what is left.

Three things count as stuck, and all of them are reported rather than acted on: an observer
reporting `different_os`, `different_app` or `outdated_ui`; the same step claimed twice; and one
step staying current for more than five minutes. The session records `session.stuck_detected` once,
sets `stuck_since`, and changes nothing else. The island shows what the session said, in the user's
words, with the offer.

`POST /sessions/{id}/replan` queues an Operation of the new kind `replan`. The worker asks the
`plan` role again, with a context carrying only the titles of settled steps, the recorded reason and
any observed anomaly — no screen content, and nothing a client asserted. Every settled step is
copied into the new version with its status, `verified_at` and a `previous_step_id` pointing at the
row it came from; a `user_reported` result is copied with it, so a step reported done is not asked
for again. Only the remainder is proposed. The result is a draft: the user reviews it on the
existing plan screen and confirms it like any other plan, which is also what makes `confirm` and
`start` work unchanged for a replanned session.

Doc 05 gained the `awaiting_user_action → analyzing` row this needs, and `tests/test_engine.py` —
the transition table written out independently of the engine — gained the same row. A failed replan
goes to `blocked` with the step as its checkpoint, exactly as a failed instruction does, because
doc 05 has no `analyzing → awaiting_user_action` row.

Current verification: 252 backend tests pass and 2 skip on SQLite, 94 web unit tests pass, and 31
browser scenarios pass in installed Chrome.

## Watching, with a surface: 2026-09-13

The consent routes from PR-14 now have somewhere to be used from. The island offers "Let Guider
watch this window"; pressing it shows the [21](21-observation-consent-notice.md) notice in full,
then the browser's own window picker, then the chosen window with the chance to paint over anything
private. Only after that does `POST /sessions/{id}/observation` get called, with the exact notice
version that was on screen. Watching is off until that last press, and one tap in the island stops
it.

`web/src/guide/watching.ts` is the only place a frame leaves the machine. It drives the tier 0/1
gate that already existed, sends at most one frame at a time, and does nothing with a verdict
except pass it on: `advance` was already committed by the server, `ask` raises one question with
one tap, `wait` shows nothing. Answering that question is recorded as a claim and a self-report,
because an observer that was not sure enough to advance has not produced evidence that the user's
answer can borrow. Masking happens in `overlay/frameSource.ts` before encoding, at up to 1,280
pixels a side; the counter shown is the server's `frames_observed` and never a number the browser
kept.

Running out of budget stops watching and says so, and the guide keeps working — that is the
supported mode, not a failure. A rate limit or a moment with no step waiting is simply a tick that
is not sent.

The browser demo refuses to watch at all, with a message saying why: it has no backend and no
vision provider, and a simulated verdict about a real screen would be an invented observation.

Not proven here: the loop has never run against a live session. That needs Supabase sign-in and a
running backend, which this environment does not have, so the tier-2 path is covered by unit tests
against a fake API plus a backend test that the exact JPEG shape the browser encodes is accepted.
With the fixture provider configured, every tick would return `unreadable` and advance nothing; the
island says so once rather than leaving a counter ticking beside nothing happening.

Current verification: 233 backend tests pass and 2 skip on SQLite, 87 web unit tests pass, and 28
browser scenarios pass in installed Chrome.

## The island on a server session: 2026-09-13

The Guide Island now runs a real session. Starting it calls `POST /sessions/{id}/start`, the step
it shows is whichever step the engine published an `Instruction` for, and it follows that session's
`GuidanceEvent` stream to learn when the next one is ready. `web/src/guide/engine.ts` stays where
it was, as the offline practice demo's reducer; `web/src/guide/live.ts` is its server-driven
counterpart.

Making that work needed the missing half of manual progression. A claim was already recorded
without verifying anything, and nothing else could move a step, so a guide with watching off could
only ever reach step one. `POST /sessions/{session_id}/steps/{step_id}/verifications` implements
doc 07's verification route, self-report arm only: it records a `user_reported` VerificationResult
with `evidence_available=false`, leaves the step `user_claimed` with no `verified_at`, and prepares
the next instruction. `next_open_step` skips steps that carry such a result, which is how the guide
advances without anything being marked verified. Evidence sent to that route is refused with
`evidence_required` rather than quietly downgraded to a self-report; objective checking arrives
with the evidence path. Doc 05 gained a paragraph recording the rule.

One bug fell out of testing: when a plan ran out of steps the last instruction stayed `ready`, so
the instruction route kept handing back a step the guide was already past. Exhausting a plan now
retires the current instruction.

The browser demo mirrors all of it — start, instruction, claim, self-report, skip and a sequenced
event log — so the Playwright suite still runs with no backend and the offline demo makes the same
promises the server does.

Current verification: 232 backend tests pass and 2 skip on SQLite, 72 web unit tests pass, and 23
browser scenarios pass in installed Chrome. Still no provider request: every role runs on the
deterministic fixture. Observation remains off in this path; the consent, counter and stop routes
from PR-14 have no surface yet, and wiring the observer loop to them is the next piece.

## Guide Engine migration: 2026-09-12

The Guide Engine migration in [20](20-guide-engine-migration-plan.md) is approved and under way. Phases 0 to 2 are merged; Phase 3 has begun.

Implemented since: the provider package and capability registry; the safety guard outside every adapter; task plans and steps; plan generation, review and version-bound confirmation; the Guide Engine as the only writer of session state, with the 05 transition table enforced; the instruction role with claims and skips; the shared frontend step engine; the Guide Island; the resumable event stream; and tiers 0 and 1 of the observer, which send nothing.

[ADR-016](adr/016-web-first-tiered-observation.md) is **adopted**. Its own gates remain shut: continuous observation stays out of production until the D06 consent notice is approved and the [011](adr/011-application-allowlisting.md) native gates exist, and `Settings.check()` is unchanged. [ADR-017](adr/017-provider-role-abstraction.md) is implemented but still formally proposed, and [ADR-018](adr/018-imported-conversation-context.md) has no implementation.

Current verification: 178 backend tests pass on both SQLite and PostgreSQL, 56 web unit tests pass, and 22 browser scenarios pass in installed Chrome. No real provider request has been made; every role runs on the deterministic fixture.

## Latest session: 2026-09-08

### Screen-guide demo

The screen-guide page opens a no-key interactive demo by default. `ScreenGuideDemo.tsx` and `demoGuide.ts` replace the earlier Python result-button walkthrough with a practice app: Settings → Appearance → Dark theme → Save. Floating hints highlight the next control. Each correct click changes sample state, shows a checking phase and automatically advances after verifying expected state. Wrong clicks do not advance; duplicate clicks cannot skip steps. Watch automatically performs sample actions only. Pause/Resume, replay and hiding the page cancel or suspend pending progression.

**Mirror my window** uses the existing capture adapter for a local preview behind the practice overlay. Hints remain anchored to sample controls, with optional browser fullscreen. Starting/changing/stopping mirroring pauses the guide. No demo screenshots are taken or sent; it does not analyze or control the selected window. Change/Stop, source loss, hiding Guider and switching to the OpenAI mode close the appropriate tracks. This is a browser overlay simulation, not a native desktop overlay.

The existing provider flow is under **OpenAI guide**. It now supports changing windows and canceling a check without stopping the preview. Replacement checks wait for cancellation to settle so a delayed cancellation cannot cancel a newer request. Follow-up text remains visible and editable during frame review; the submitted goal and question are fixed for the request. Late picker results and pagehide cleanup no longer leave an active-looking connection or stale preview.

Web verification: 13 unit tests, all 9 screen-guide browser scenarios, and the production web build passed. The six interactive-demo scenarios cover click-driven verification, wrong-click rejection, automatic playback, pause during playback/verification, restart cancellation, mirrored overlays, source switching/stop/mode cleanup, browser fullscreen, picker dismissal, mobile hint bounds and keyboard actions. Three provider-flow scenarios cover reviewed submission, stopping a pending request, cancellation ordering, follow-up text and previous-step context. Desktop, mobile and mirrored-overlay screenshots were visually inspected. Browser capture uses real media tracks with a simulated source picker, and provider responses are simulated; no real API call or native picker interaction is claimed. Production/native release gates below remain open.

To try it: run `npm start` and open `http://127.0.0.1:5173/#live`. The demo also runs with only `npm run dev` from `user-mode/web`; its walkthrough and local mirroring require no backend.

### Root npm/pnpm launcher

Added a private root `package.json`, npm/pnpm root lockfiles and `scripts/guider.mjs`. Run `npm install` then `npm start`, or `pnpm install` then `pnpm start`. The install hook prepares the existing locked frontend and Python environments. The launcher applies migrations, starts loopback Vite/Uvicorn together, rejects occupied ports and closes both services on Ctrl+C. Node.js 22.12+, Python 3.13 and uv remain prerequisites. `dev`, `build`, `test` and explicit `setup` commands are also available.

Verified root npm and pnpm installation, pnpm startup, HTTP 200 responses from the web app and API contract, and rejection of a second start. A launcher smoke check emitted SIGINT and verified that both services became unreachable after shutdown. Windows shutdown closes the specific child process trees, including the Python virtual-environment launcher. Root build and both npm/pnpm test commands passed (11 web tests and 39 backend tests); pytest temporary files and cache use `.local/tests`. No real OpenAI request was made.

The previous session added a local live guide on top of the screenshot development slice: browser window/tab selection, local preview, user-triggered frame capture, crop/hide review, and a personal OpenAI connection for one-step guidance. [ADR-015](adr/015-browser-observation-and-personal-cloud.md) records this accepted exception to the original implementation order. The original first-slice report below remains historical evidence.

This continuation finished the missing startup instructions and specification cross-references, exported the local-guide OpenAPI/component schemas, and added a typed connection response. It also fixed a response-policy bug: a provider response marked `blocked` could be downgraded to `needs_context` when its action fields contained a restricted term. The response now stays blocked, its action fields are cleared, and the frontend's existing blocked branch stops sharing. A parametrized backend regression test covers this case.

Current verification: **39 backend tests and 11 web unit tests passed**. Backend Ruff and the web production build passed. Generated contracts include the connection, cancel, disconnect and check endpoints. Backend tests use simulated OpenAI HTTP responses and synthetic images; no real key or paid provider request was used.

All **4 browser scenarios passed across the initial run and a focused rerun** in installed Chrome: reviewed cloud submission/disconnect, cancellation/stale-answer rejection, screenshot history/deletion/responsive layout, and keyboard masking. The cloud journey initially timed out during page loading at the default 30-second test limit; it passed in 9.1 seconds when rerun with a 60-second test limit. Browser tests simulate the source picker and provider while exercising actual browser media tracks, capture, image review and UI handling.

Validation environment: uv required access to its external dependency cache. The default pytest temporary directory and existing Playwright output directory had Windows permission errors; reruns used fresh `.local/pytest-resume-20260908a` and `test-results/resume-20260908a` / `resume-20260908b` directories. No existing test artifacts were manually deleted.

### Resume here

1. Run `npm install` and `npm start` (or `pnpm install` and `pnpm start`) at the root, then open `http://127.0.0.1:5173/#live`. See the root [README](../../README.md). Supabase is not required for this local workflow.
2. Manually validate the native Chrome/Edge source picker and a real OpenAI account/model response using a nonsensitive synthetic window. Enter the personal API key only in the app. Real provider access and billing have not been verified.
3. Check source loss, hiding Guider, explicit Stop and Disconnect in that manual session. The sharing permission lasts 15 minutes and the in-memory cloud connection lasts 30 minutes; restarting requires an explicit user gesture.
4. Keep the production, native-overlay and account-provider gates listed below open. Saved screenshot tasks still use the fixture provider; live answers are ephemeral and do not become saved task history.

All project files remain untracked on an unborn `main` branch; this continuation did not create a commit or configure a remote.

## Original first development slice

Date: 2026-09-07. Status: **phase 0/1 partial implementation**, not a completed release gate. The original inspection report describes the pre-code baseline. The specifications remain the target; the limits below are outstanding work, not relaxed product requirements.

## Implemented

- Independent React/TypeScript/Vite web and FastAPI/Pydantic/async SQLAlchemy backend manifests and dependency locks; WPF shell manifest.
- Supabase-only backend authentication: asymmetric signature, issuer, audience, role, UUID subject, expiry/not-before, cached JWKS, active-user and revocation checks. Tests replace trusted key discovery with an in-memory public key while still exercising signature/claim verification. No runtime test-auth switch exists.
- Task/session creation and owner-scoped reads/history; strict request validation, safe error envelopes, session version checks, persisted idempotency receipts and content-free session events.
- Manual single-image intake, byte/dimension/pixel/format/frame bounds, metadata removal, private authenticated content reads, local storage adapter and 24-hour media expiry.
- Crop, opaque masking, Undo, exact-pixel preview, keyboard coordinate entry, explicit review before upload, replacement and deletion in the web interface.
- Durable queued analysis Operations, a local polling worker, validated fixture-provider output, answer-only behavior, pause/stop cancellation, and rejection of outdated operations.
- Image deletion removes stored bytes and dependent analysis, clears result references and tombstones dependent idempotency receipts. Repeated deletion returns the same receipt.
- Synthetic fixture explanation with a viewer marker; arbitrary images receive an explicit development limitation and no invented observation.
- A separate browser-memory demo when web Supabase configuration is absent; no API bypass, persistent demo accounts, or external vision calls.
- Generated contracts for implemented routes. No unimplemented future handlers return fake success.

## Verification scope

API tests cover valid signed requests, invalid claims/signatures, user revocation, owner and cross-task isolation, retry conflicts, stale uploads, refused observation, fixture results, deletion before and after analysis, media expiry, paused manual help, decoder limits and safe validation errors. Web unit tests cover redaction boundaries. Playwright exercises the example, deletion, keyboard masking and small-screen layout.

First-slice validation: **24 backend tests, 6 web unit tests and 2 Playwright tests passed**. The web production build and backend Ruff checks passed; `alembic upgrade head` and `alembic check` passed against local SQLite. Desktop (1440px) and mobile (390px) screenshots were visually inspected. Browser tests used installed Chrome through `GUIDE_BROWSER_CHANNEL=chrome`; the default Playwright Chromium download was unavailable, and Edge timed out creating its second test context.

SQLite checks are development evidence only. PostgreSQL concurrency, native PKCE/overlay, production Supabase login and real provider integration are not certified by these tests. The Docker engine was unavailable and the .NET SDK was not installed during the first coding session.

## Remaining before phase 1 can ship

1. D01/D02/D06 provider, hosting and privacy decisions; a reviewed provider and actual Supabase integration test. Current analysis is a deterministic fixture only.
2. Isolate decoding in an OS-restricted process with enforced memory/time/CPU limits and private in-memory multipart handling. The current bounded decoder runs on a thread in the development API process. Finish ICC/sRGB conversion, animated-file rejection before browser normalization and client sensitive-data warnings.
3. Production encrypted private object storage, staged upload reconciliation, transactional deletion fault recovery, provider derivatives, multi-worker leases and distributed quotas. Current worker and per-owner serialization target one local API process; image/create/analysis quotas are implemented, but ingress/read/delete profiles and full audit persistence remain open.
4. Complete PostgreSQL migrations and tests: native UUID/JSONB types, enum/check constraints, partial uniqueness, lineage FKs, outbox certification and durable deletion races. The initial migration uses portable development column types and composite child-owner FKs.
5. Task/session/account erasure, full 30-day content retention, replay/audit/idempotency cleanup, orphan sweeper, deletion-failure retries and backup erasure ledger. The minute-based media sweeper handles image TTL, not the entire lifecycle model.
6. Remaining phase-1 wire surface, including session upload alias; persistent screenshot inventory/recovery, resumable task routing, complete history pagination in the UI and durable terminal summaries. API history pagination exists; the web currently displays its first page. Priority pause and stop work; Resume/planner/verification are not implemented.
7. Accessible sign-in modal focus trapping and exhaustive contrast/keyboard/200% zoom checks; CSP and deployment origin policies; end-to-end auth loss/sign-out/refresh cases.
8. Native build and synthetic PKCE spike. The WPF scaffold has no capture, token handling or overlay feature.

Production startup is hard-gated in `Settings.check()`. Do not remove the gate solely to deploy this preview.

## Traceability of current evidence

| Requirements | Current code/tests | Status |
|---|---|---|
| R01/R02, UX01/02 | Web task composer; `test_create_retry_is_private_and_idempotent` | Partial; route persistence and full authentication UX remain |
| R03/R16, UX03, T03/T16 | Image editor, `media.py`, deletion/expiry/replacement tests, browser masking test | Partial; isolated decoder and production storage remain |
| R11/R12/R20, T11/T20 | Pause/stop, epoch/version invalidation, queued-work cancellation | Partial; full state machine and terminal summaries remain |
| R15, T15 | Asymmetric JWT and owner/child tests | Partial; real Supabase integration and native auth remain |
| R18/R19/R23/R30 | Fixture adapter, generated contracts, quotas, independent manifests | Partial; full policy, audit and deployment certification remain |

This page supplements [17](17-traceability-matrix.md) and [15](15-mvp-implementation-plan.md); it does not mark T01–T40 or either phase complete.
