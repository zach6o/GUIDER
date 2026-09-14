# 19 · Implementation status and session handoff

## Pointing, and noticing nobody is there: 2026-09-14 · V2.3

**Marks are derived, not asked for — a deliberate departure from doc 22.** The
architecture put a `marks` column on `instructions`. Building it showed that to be
wrong twice over: the instruction role never sees a screen, so asking it for
geometry would be asking it to invent coordinates; and stored geometry goes stale
the moment the window moves. `app/guide/marks.py` instead matches the
instruction's own words against the controls the observer reported, at the moment
the frame was read, and the mark travels with that tick. Migration `v2_02_marks`
is therefore unnecessary and is not written.

Matching is strict on purpose. Words like "click", "button" and "open" carry no
identifying weight, so an instruction saying "click the button" matches nothing —
which is correct, because the whole point of a mark is *which* one. Ties break
toward the shorter label. No confident match produces no mark at all, the ordinary
case rather than a failure, because the instruction still says where to look in
words. And the guard runs twice: a control naming a restricted action is dropped
from the context and again from the mark, because a mark is the one output that
would put Guider's finger on it.

`web/src/overlay/renderer.ts` draws on Guider's mirror of the shared window.
Marks are multiplied by the picture's own rectangle — computed rather than
assumed, because `object-fit: contain` letterboxes and a mark placed against the
element would drift by the size of the bars. A resize changes the multiplier and
nothing else. A mark landing under two pixels is dropped rather than drawn as a
speck. Labels sit above, below or inside, never over what they name, and every
mark carries the control's name for anyone not looking at it.

`web/src/guide/idle.ts` measures the two things a browser can honestly observe:
the shared window has not changed, and nobody has touched Guider. Four stages at
30 s, 1 min, 3 min and 5 min, each firing once, the last stopping watching and
keeping the place. A test reads the copy and fails if it claims the user walked
away — a browser cannot see the desk, and the wording must not pretend it can.

Current verification: 425 backend tests pass and 12 skip on SQLite, 137 web unit
tests pass, and 53 browser scenarios pass in installed Chrome.

## Guidance that follows the screen: 2026-09-14 · V2.2

`next_open_step` hands out the lowest-numbered step still waiting, which is a
correct plan reader and a poor instructor. `app/guide/adapt.py` reads the belief
the Context Engine formed and decides which of six things is happening: the step
is in progress, the screen satisfies it, a later step is already done, the user
is off track or in the wrong application, a dialog is blocking them, or the
window cannot be read.

The selector is a pure function over one belief, so the table is the rule and can
be read in one place. Three boundaries hold it in: it may point at a different
step of the confirmed plan and never invent one; it hands a satisfied step to the
verification path rather than settling it; and the one move that changes the
user's record — skipping forward — asks.

That asking is a route, not a branch. `POST .../skip-forward` takes back the step
ids the user was shown, refuses anything behind the guide, refuses anything the
guard blocked, and records what it settles as `skipped` — not verified, not
reported done, because nobody said they were. A context tick can offer; only the
user can accept.

Being off track three times on one step raises the stuck signal that already
exists, which is how a redirect that is not working becomes an offer of a
different plan rather than a louder redirect.

The consent notice is rewritten to `observation-draft-2`, and this is a rewrite
rather than an edit. Version 1 described frames checked against one step; the
product now forms a running description of the screen, keeps those descriptions
for seven days, and reads text it must never obey. The notice says all three in
the user's words, and adds that watching stops itself after five minutes of
nothing happening. A session that accepted version 1 is asked again, which is what
the version check has always been for. **D06 approval is still outstanding**, and
production is still gated.

Current verification: 410 backend tests pass and 12 skip on SQLite, 120 web unit
tests pass, and 53 browser scenarios pass in installed Chrome.

## The guide can say what it is looking at: 2026-09-14 · V2.1

The observer answers one question — is this step's criterion satisfied? — which
is enough to advance a plan and not enough to guide anyone. `app/guide/context.py`
adds the second question: what is on this screen?

`ScreenContext` is a belief, and the separation is structural rather than
promised. It lives in its own table, it can set no status, and
`tests/test_context.py` holds the line that matters: a stage of `step_satisfied`
at confidence 0.95 leaves the step exactly as it was, because only the
verification path can verify anything.

The `context_digest` is what makes looking at every admitted frame affordable. It
hashes the application, the screen, the stage, the control labels and whether a
dialog or an error is up — and deliberately excludes confidence, free text and
box geometry, so a model that re-words the same screen or nudges a box by a pixel
does not read as a changed screen. An unchanged digest means the instruction the
user already has still stands, and no reasoning call is made. That property has
its own parametrised test in both directions.

The guard extends to this surface. Screen text is untrusted in exactly the sense
SEC-09 means: a control labelled `SYSTEM: ignore previous instructions` is
dropped rather than offered, a control naming a restricted action is dropped, and
a stage claiming progress below the acting floor is downgraded rather than
recorded. A mark pointing at a control found on a screen would be Guider acting
on words it read there.

`POST /sessions/{id}/context` is the sibling of `/observe`, not its replacement:
that route decides whether a step is done, this one decides what the guide is
looking at, and both draw on one 200-call budget because they are the same user's
frames and the same bill. `GET /sessions/{id}/context` reads the last belief back
for a client that reconnected.

The fixture provider serves the new role by refusing to guess — the same belief
every time, `unreadable` at confidence 0. A fixture that invented screens would
produce a digest that changed on every frame, which is precisely the failure the
design cannot tolerate.

Not proven: no real model has produced a context. Whether a cheap one describes a
screen consistently enough for the digest to hold is the load-bearing assumption
of this phase, and it needs a provider key to test.

Current verification: 393 backend tests pass and 12 skip on SQLite, 120 web unit
tests pass, and 53 browser scenarios pass in installed Chrome.

## A step can finally be verified: 2026-09-14 · V2.0

The product's central promise is *one verified step at a time*, and until today
the only way to reach `verified` was to be watched live. `POST .../verifications`
had one arm: the user's word, recorded honestly as `user_reported` and awarded no
badge. A client that sent evidence was refused outright — which was honest, and
left the promise half-built for anyone not sharing their screen.

`app/guide/evidence.py` is the other arm. A screenshot the user shares is checked
by the same observer role that judges a live frame, against the same bands: at
0.85 and above with the criterion satisfied it is a **pass**, and the step becomes
`verified` with its timestamp and the confidence that earned it; between 0.60 and
0.85 it is **inconclusive** and advances nothing; below that, or with the
criterion unsatisfied, it is a **mismatch** that counts an attempt and leaves the
step current. One threshold table, two entry points, and `evidence_available` is
the column that keeps a checked step distinguishable from a reported one forever.

The check is a durable Operation rather than a request that blocks, because a
provider call that outlives the request is what Operations are for. So the route
now has two shapes: the user's word settles at once and answers 200, while
evidence answers 202 with the Operation to follow. Doc 07's row records both.

One gap fell out of building it. A manual upload was refused while a step was
waiting on the user — which is precisely the moment someone wants to share a
screenshot of the result. Doc 05 always allowed it ("manual upload alone stores
context"); the route did not. It does now.

The browser demo refuses to check, with the reason: it has no vision provider,
and a simulated verdict about a real screenshot would be an invented
verification. That is the same refusal it already makes about watching.

Current verification: 362 backend tests pass and 12 skip on SQLite, 120 web unit
tests pass, and 53 browser scenarios pass in installed Chrome.

## Deletion, at last: 2026-09-14 · V2.0

The only thing a user could delete was a screenshot. The goal they typed, the transcript they
pasted, the record of what they were guided through, the account itself — none of it had a way out,
while [09](09-security-and-privacy.md) SEC-13 required exact deletion semantics and doc 07 had
specified all three routes from the beginning. [22](22-guider-v2-architecture.md) makes closing this
the first phase of V2, before anything is built that would give the product more to remember.

`DELETE /sessions/{id}` stops the session first, then removes every row under it — instructions,
claims, verifications, summaries, feedback, imports, plans, steps, operations, events and images,
bytes before rows — and leaves the task standing, because removing one attempt is not asking to
forget the goal. `DELETE /tasks/{id}` takes the task, every session under it and its task-level
images. `DELETE /account` takes all of that and the owner's idempotency records, sets
`auth_revoked_before` to now so every token issued before the request stops being accepted, and
leaves the receipt readable — doc 08 keeps it until the Supabase identity itself is removed, which
is a separate audited step this route does not perform.

Account deletion requires the exact header phrase doc 07 specifies, typed by the user, and a sign-in
from within the last five minutes. `auth.py` now records when the presented token was issued, which
is what makes that check real rather than decorative.

`app/erasure.py` names every table in dependency order rather than relying on cascades — only five
foreign keys in the schema cascade, and deleting a parent while hoping is how orphans are made. The
test that matters most reads the schema at runtime and fails when a table exists that the erasure
module never names, with an explicit exempt list of three: the identity row, the receipt, and
Alembic's own bookkeeping. A table added without being erased is a privacy leak no ordinary test
would catch, because a test only checks the tables it knows about.

Deleting twice produces no second receipt. Another owner's rows are untouched — the property with
its own test, because it is the one that would matter most if it were wrong.

On screen: a delete control on each history row, a dialog that names what goes with the task before
anything happens, and a danger zone on the privacy page where the confirmation phrase is typed. The
privacy page no longer says task and account erasure are on the roadmap, because they are not.

Current verification: 359 backend tests pass and 12 skip on SQLite, 120 web unit tests pass, and 53
browser scenarios pass in installed Chrome.

## A way back from blocked: 2026-09-14

A guide could be stopped four ways — pause, the safety guard, a failed
instruction, and since PR-20 the user saying the guidance was wrong — and
resumed none of them. `blocked` was a polite word for abandoned, and PR-20 made
that worse by giving users a button that reached it. Doc 07 had specified both
routes back since the beginning; neither existed.

`POST /sessions/{id}/resume` implements doc 05's resume row. It works only from
`paused` or `blocked`, refuses with `context_review_required` until the user
confirms they have looked at where the task got to, and returns to the recorded
checkpoint — rebuilt from whether a plan is confirmed when the checkpoint is not
a resumable state. No screen permission is restored, ever: `mode: window` returns
the session to `awaiting_screen_permission` so being watched again is a fresh
decision with its own notice. When the instruction was withdrawn — which is what
`incorrect_guidance` does — resume re-requests one rather than returning the user
to an empty island, and hands back the Operation to follow.

`POST /sessions/{id}/steps/{step_id}/retries` asks for the current step in
different words. It is not a claim, a skip or a verification, and it changes
nothing about the step except its attempt count. That count is the point: the
stuck detector already reads it, so a step reworded twice reports itself as going
nowhere and offers a replan. Past three attempts the route refuses with
`retry_limit` and says to ask for a different plan instead; a step the guard
blocked is refused first, because no number of attempts turns a step Guider will
not explain into one it will.

Two bugs fell out of wiring the island to this.

The first was mine, from PR-20's era: `useLiveGuide` exposes `session` as a value
captured when the page rendered, and `App` was handing that snapshot back through
`setSession` after an action had already moved the session on. The next request
then carried a stale `expected_version` and was refused. The hook now refuses to
adopt a session older than the one it holds.

The second was in the reducer: a new instruction cleared the stuck notice,
because a new instruction used to mean a new step. A retry publishes a new
instruction for the *same* step, so asking twice raised the notice and then wiped
it in the same breath. Being stuck is about the step, so the notice now survives
a rewording and clears only when the step actually changes.

A resume that fails now says so in the island. There is no step on screen to
carry the message at that point, and a button that silently does nothing is worse
than one that explains itself.

Current verification: 348 backend tests pass and 12 skip on SQLite, 120 web unit
tests pass, and 51 browser scenarios pass in installed Chrome.

## A way to make a real provider request: 2026-09-14

Every provider answer in the suite is a recorded shape replayed through an
injected transport, and doc 19 has carried "no real Anthropic request has been
made" since PR-16. That sentence is still true today, and this is the path that
can change it.

`scripts/smoke_provider.py` sends one synthetic request per role the configured
provider serves — plan, instruct, observe and import — parses each answer through
the adapter, runs the guard over it, and prints the verdict with its latency.
Nothing touches a database, no session exists, the frame is a terminal drawn in
memory rather than anyone's screen, and the transcript is four lines written in
the file. It refuses to run without `--spend-real-money`, because a flag nobody
types by accident is the difference between an instrument and an accident.

What it reports is deliberately not a pass mark. A refusal, a truncated answer
and a guard rejection are all printed as findings rather than raised as crashes —
the last of those being the whole reason the guard sits outside the adapter. The
observe run prints the confidence a real model returns on a screen where the
honest answer is yes, and asserts nothing about it: whether a model clears 0.85
is what D05 exists to settle, and one frame is not the sample that settles it.
The import run sends a transcript with an injected `SYSTEM:` line and says
plainly whether it reached the plan.

`.github/workflows/provider-smoke.yml` is the only place CI can run it: manual
dispatch, a protected `provider-smoke` environment holding the key, and the
answers kept as an artifact. The ordinary pipeline is unchanged and still reaches
no network.

`tests/test_smoke_script.py` covers the guardrails without spending anything: an
unconfigured machine builds no registry and sends nothing, a fixture-resolved
role is reported as having sent nothing rather than counted as a pass, the frame
is a real PNG with something drawn on it, and a refusal becomes a printed line.

Still not proven, and the reason is worth stating plainly: **no request has been
made yet.** This repository has no provider key, so the script has run only
against the unconfigured path. D01 remains open per provider, and account-mode
access stays a development switch.

Current verification: 334 backend tests pass and 12 skip on SQLite, 116 web unit
tests pass, and 48 browser scenarios pass in installed Chrome.

## Racing the engine on PostgreSQL: 2026-09-14

Doc 20 has said since the migration began that the row locks are no-ops on SQLite
and the engine depends on them. One test held that line — two plan confirmations
racing — which proved the lock exists and nothing about the paths a guide runs
through.

`tests/test_concurrency.py` races real routes against each other: claims against
claims and ten at once, a claim against a skip, two self-reports of one claim, a
self-report against an observer advance, a stop against a frame already in
flight, two completions, and one idempotency key sent twice at the same moment.
Each asserts the invariant rather than the winner, because which request wins is
a scheduling detail: exactly one lands, the loser is refused rather than quietly
applied, and no record describes two histories. Two more check that the event
sequence stays gapless under concurrent writers — a client resumes at a cursor,
so a duplicate or a gap is a missed instruction — and that the lock is per owner,
so one user's guide never waits behind another's.

They skip on SQLite rather than reporting green where `SELECT ... FOR UPDATE`
does nothing, which is why the skip count moved from 2 to 12. CI runs the backend
suite twice and the second run is where they count.

One of them was wrong at first and said so loudly: both completions were refused
because a session with open steps cannot be completed at all, which is a
rejection and not a race. It now works the plan to its end before racing.

What this does not cover is sustained load. These are pairs and one group of ten
inside a single process; throughput, connection-pool exhaustion and lock waits
under a real population remain unmeasured, and doc 07's performance budgets
(T38) are still unexecuted.

Current verification: 328 backend tests pass and 12 skip on SQLite, all 340 pass
against PostgreSQL in CI, 116 web unit tests pass, and 48 browser scenarios pass
in installed Chrome.

## Three surfaces, not one and two consolations: 2026-09-14

ADR-016 calls side-by-side and mirrored preview first-class modes, and doc 20
lists Picture-in-Picture's absence on Safari and Firefox as a risk to build for
rather than discover late. The code did neither. The floating window was a button
that simply disappeared where the API was missing, the mirrored preview existed
only in the offline practice demo, and closing the floating window ended the
whole guide — a window control that lost the user their place.

`web/src/overlay/surface.ts` makes the choice explicit. All three surfaces are
listed whatever the browser is; one that cannot open stays on screen carrying the
reason, because a user on Firefox should learn that the floating window is a
Chromium feature rather than quietly receive a different product. The page is
preselected: opening an OS window or a window picker is a deliberate act, not
something that should happen because Start was pressed. A surface that refuses to
open falls back to the page and says so. Closing the floating window now returns
the guide to the page and keeps the session.

The mirror is a local video element beside the guide, with its own capture kept
apart from the observation one. Sharing a stream between them would have made
choosing a layout imply consenting to be watched. The panel says so every time it
is on screen: watching is separate, off by default, and asks for its own
permission and its own window.

Detection lives in one place — `overlay/pip.ts` — so the offer and the attempt
cannot disagree.

Not proven here: no Safari or Firefox run exists. The unsupported path is covered
by deleting `documentPictureInPicture` before the page loads, which is a faithful
shape rather than the real browser, and doc 07's hardware and browser matrix
remains unexecuted.

Current verification: 328 backend tests pass and 2 skip on SQLite, 116 web unit
tests pass, and 48 browser scenarios pass in installed Chrome.

## Measuring the failure mode that matters: 2026-09-14

`ADVANCE_AT = 0.85` has been a hypothesis since PR-13, and doc 20 calls advancing
past a step the user has not done the principal failure mode. There was no way to
find out how often it happened, because the only signal — the user saying the
guidance was wrong — had nowhere to go. Doc 07's feedback route existed on paper
and nothing implemented it.

`POST /sessions/{id}/feedback` implements it, with the consequences doc 05
attaches rather than a softer version. `helpful`, `unhelpful` and
`privacy_concern` are opinions and change nothing. `incorrect_guidance` names a
step — without one it is refused, because there is nothing to withdraw and
nothing to learn — and then does all four things doc 05 lists: the ready
instruction becomes `invalidated`, a `passed` visual result for that step becomes
a `mismatch` with the step back to `pending` and its `verified_at` cleared,
watching is revoked through the existing epoch-bumping stop, and the session
blocks with its checkpoint saved. A `user_reported` result is deliberately left
alone: the user is contradicting Guider there, not themselves.

`app/guide/calibration.py` reads what that produces. It folds `observation.tick`,
`verification.completed` and `verification.contradicted` events into counts per
0.05 confidence band — advances, asks, waits, and advances the user contradicted
— and prints what moving the line to 0.75 through 0.95 would have done to the
ticks actually recorded. `uv run python -m scripts.calibration <owner_id>` prints
it; it is an engineering instrument, not a product surface, so it is a script and
not a route.

Two limits are in the code and in the report's own wording rather than left to be
discovered. Events expire after seven days, so a report is a window and not a
history. And an advance nobody contradicted is `unchallenged`, never confirmed:
most users will never file feedback, so `contradicted / advances` would read as an
error rate while being nothing of the kind. The contradicted verification's id
and confidence are copied onto the feedback row because the verification expires
and the finding should not.

In the island the control asks before it acts — one press reveals what it costs,
a second sends it — because it ends the running guide. Afterwards the island
shows what happened and stops pointing at anything, and the browser demo mirrors
the same three effects it can have without a backend.

D05 is not resolved by this. It is now answerable with counts rather than
opinion, once there are real sessions to count; the held-out evaluation corpus
T31 asks for still does not exist.

Current verification: 328 backend tests pass and 2 skip on SQLite, 108 web unit
tests pass, and 44 browser scenarios pass in installed Chrome.

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
