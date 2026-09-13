# 05 · Guide session state machine

Status: proposed MVP. This is the authoritative `GuideSession.state` vocabulary. UI labels such as “stopped” are not additional session states. Data enums: [08](08-data-model.md); routes: [07](07-api-contracts.md).

## Model and invariants

`idle` is a local pre-task state, not a persisted session. Task creation atomically creates GuideTask and GuideSession in `task_created`. Session owns `state`, `state_version`, `control_epoch`, `checkpoint_state`, `current_step_id`, `confirmed_plan_version`, `controller_device_id`, `observation_mode`, `outcome` and expiry timestamps. `observation_mode=screenshot_only|window` expresses selected mode, never proof of a valid permission.

Only the backend Orchestrator commits authoritative state. Authenticated user commands trigger transitions; Windows owns immediate local capture safety and reports its action. Every session-affecting mutation validates owner/current version, increments `state_version` and writes a sequenced GuidanceEvent/outbox entry, including same-state edits. Read/lease-heartbeat/operation-poll bookkeeping does not advance state_version. Every media/provider operation binds plan/instruction version, screenshot version, control epoch and the post-admission session state version; stale results are discarded. Provider work may commit only while it remains the current operation. Nonsemantic feedback/heartbeat metadata must not spuriously invalidate it. Cancel/pause/stop/revoke/delete take priority and increment epoch.

`paused` and `blocked` preserve a stable checkpoint: `task_created`, `awaiting_user_confirmation` or `awaiting_user_action`. Transient states never become resume targets. A paused manual explanation uses an Operation record without changing session state. Session state is flat; operation and step statuses are separate enums.

## States

| State | Meaning / persisted checkpoint and side effects |
|---|---|
| `idle` | No persisted task; local draft only |
| `task_created` | Goal and initial session saved; context/plan work may begin |
| `analyzing` | Durable analysis/planning operation pending; return checkpoint is task_created or awaiting_user_confirmation |
| `plan_ready` | New immutable plan version and steps saved; cannot start yet |
| `awaiting_user_confirmation` | Displayed plan version requires approval |
| `awaiting_screen_permission` | Confirmed plan and explicit live request; no capture yet |
| `active` | Confirmed session admitted; dispatch boundary, not a claim that observation is on |
| `capturing` | One requested native still acquisition with current grant and lease |
| `processing` | Context or instruction operation pending; no unrestricted capture |
| `instruction_ready` | Validated current instruction persisted; ready for rendering |
| `awaiting_user_action` | Current instruction shown; user works; no automatic advancement |
| `verifying` | Verification operation evaluates claim against fresh evidence |
| `blocked` | Missing context, unsafe/unsupported request or repeated mismatch; capture revoked; manual recovery available |
| `paused` | User/system interruption; capture revoked, pointer absent, readable checkpoint retained |
| `stopping` | Capture authorization already revoked, outstanding work canceled, deterministic summary cleanup pending |
| `completed` | Terminal with outcome `achieved`, `user_reported` or `stopped`; no capture |
| `failed` | Terminal unrecoverable integrity/service failure after recovery exhausted; outcome `failed` |
| `expired` | Terminal timeout; outcome `expired`; retained task may start a successor |

## Transition table

Every actual persisted state change emits `session.state_changed` with `{from,to,reason,state_version,control_epoch}`; same-state commands emit only their named resource event. Named secondary events below follow the state event in the same ordered stream. Transitions not listed in the table or its explicit diagnostic exceptions are rejected with `409 invalid_transition`. Any nonterminal state may take priority pause/stop/expiry as specified.

| From → to | Trigger / actor | Guards, persistence and secondary event |
|---|---|---|
| idle → task_created | Create task / user | Owner/goal valid; insert task/session; `task.created` |
| task_created → analyzing | Analyze or plan / user via Orchestrator | Accepted evidence or sufficient goal; insert Operation; `operation.started` |
| analyzing → task_created | Explanation-only result / Orchestrator | Persist analysis; `analysis.ready`; no plan implied |
| analyzing → awaiting_user_confirmation | Answer-only analysis requested during plan review / Orchestrator | Preserve plan/version/confirmation unless answer requires proposed plan revision; `analysis.ready` |
| analyzing → plan_ready | Plan result / Orchestrator | Valid safe 1–12 step plan; persist new version; `plan.ready` |
| plan_ready → awaiting_user_confirmation | Plan made available / Orchestrator | Durable transition independent of delivery; `plan.confirmation_required` |
| awaiting_user_confirmation → analyzing | Revise/regenerate / user | Invalidate confirmation and old instructions; new Operation |
| awaiting_user_confirmation → awaiting_user_confirmation | Confirm plan / user | Exact plan version, confirmation record; `plan.confirmed`; ready for Start |
| awaiting_user_confirmation → awaiting_screen_permission | Start live / user | Confirmed version and registered controller; `permission.required` |
| awaiting_user_confirmation → active | Start screenshot-only / user | Confirmed version; `session.started` |
| awaiting_screen_permission → active | Valid local grant / native user; or explicit screenshot-only Start | Verify device/scope/nonce for grant; denial alone stays awaiting; fallback emits `session.started` with observation off |
| active → capturing | POST capture intent / native user through Orchestrator | Current grant/lease/scope and intent=context; persist CaptureIntent; `capture.requested` |
| active → processing | Existing evidence sufficient or screenshot-only context / Orchestrator | Bind evidence/version; `operation.started` |
| capturing → processing | Accept image / native | Epoch/grant/image validated, metadata persisted; `screenshot.accepted` |
| processing → instruction_ready | Valid instruction result / Orchestrator | Risk gate; persist instruction/version; `instruction.ready` |
| instruction_ready → awaiting_user_action | Instruction published / Orchestrator | Current instruction in API/event stream; `step.awaiting_action`; delivery ack optional |
| awaiting_user_action → verifying | Request verification / user | Done creates `user_claimed` separately. Verification needs accepted new evidence or explicit self-report; `verification.started` |
| awaiting_user_action → capturing | POST capture intent / native user | Intent=context for recheck/revision, or intent=verify with CompletionClaim; matching image admission schedules instruction or verification operation |
| processing → verifying | Accepted evidence for verification / Orchestrator | Current step/claim bound; create VerificationResult pending |
| verifying → active | Evidence passed and more steps / Orchestrator | Step verified; current step advances; `verification.completed` |
| verifying → awaiting_user_action | Mismatch/inconclusive, attempts remaining / Orchestrator | Result and reason saved, old pointer removed; request context or revised instruction through processing |
| verifying → awaiting_user_action | Self-report result / Orchestrator | Save user_reported result, step remains user_claimed; offer objective recheck or explicit task completion with outcome=user_reported; no verified pass |
| awaiting_user_action → analyzing | Replan after stuck or anomaly / user | Confirmed plan required; current instruction retired and pointer cleared; settled steps are carried into the new version untouched; `session.replan_requested`, then `plan.ready` and `plan.confirmation_required` |
| awaiting_user_action → processing | Analyze/Recheck referencing new manual screenshot, follow-up or retry / user | Manual upload alone stores context; explicit analysis/instruction request determines explanation/revision; no automatic step pass |
| processing → awaiting_user_action | Answer-only response / Orchestrator | Preserve current instruction; `answer.ready` |
| verifying → completed | Final goal evidence passes / Orchestrator | All required steps verified; summary `achieved`; revoke grants; `session.completed` |
| awaiting_user_action → completed | Complete with self-report / user | Remaining nonblocked uncertainty disclosed; summary `user_reported`; no verified badge |
| Any nonterminal except stopping → paused | Pause, Cancel operation, network/auth loss, lock, suspend, controller loss / user or watchdog | Increment epoch, revoke grants, cancel work; save stable checkpoint; `permission.revoked` |
| Any working state → blocked | Unsafe/context failure or repeated mismatch / safety/Orchestrator | Save reason and checkpoint; revoke grant; `session.blocked` |
| paused/blocked → checkpoint | Resume/retry / user | Re-authenticate, review context, clear recoverable reason. Confirmed step checkpoint returns through active; unconfirmed plan returns awaiting_user_confirmation. No grant restored |
| paused/blocked → awaiting_screen_permission | Resume choosing live / user | Confirmed plan, recoverable reason resolved, new local grant required |
| Working state → awaiting_user_confirmation | Material plan edit / user/Orchestrator proposal | Stop capture, invalidate confirmation, persist new version; user must confirm; no scope creep |
| Any nonterminal → stopping | Stop, close, sign-out, deletion / user or safety | Revoke and epoch-increment before cleanup; `session.stopping` |
| stopping → completed | Bounded cleanup / Orchestrator | Summary outcome stopped (or deletion tombstone); local overlay already gone; `session.completed` |
| Any nonterminal except stopping → expired | Expiry watchdog | Revoke/cancel, summary expiry; `session.expired` |
| Any nonterminal except stopping → failed | Unrecoverable corruption/failure / Orchestrator | Revoke/cancel, safe error summary; `session.failed` |
| completed/failed/expired → no transition | Continue previous / user | Create new session in task_created, `previous_session_id` set; original remains terminal |

“Working state” means active/capturing/processing/instruction_ready/awaiting_user_action/verifying/analyzing; risk-gate failures during intake/planning also allow task_created/plan_ready/awaiting_user_confirmation/awaiting_screen_permission → blocked. A new image alone does not unblock a prohibited task. Same-state commands (claims, confirmations, accepted manual context and content-free feedback) emit their resource event; emit session.state_changed only when state actually changes. Same-state session-affecting changes increment state_version. Nonsemantic feedback and lease renewal use their own row versions and do not invalidate an active operation.

Being stuck is a report, never a transition. When an observer sees a screen that no longer matches the plan, when one step is claimed repeatedly, or when a single step stays current far longer than it should, the session records `session.stuck_detected` once and sets `stuck_since`. Nothing else changes: no state moves, no step is failed, and the guide keeps offering the same step. What it buys the user is the offer of a replacement plan, which is a separate explicit request. A replan produces a draft like any other plan, so the roadmap is confirmed before anything continues, and a failed replan leaves the confirmed plan exactly as it was.

A self-report result leaves the step `user_claimed` and records `user_reported`, as the table says, and it also releases the guide: the reported step is no longer handed out as the open step, so the next instruction is prepared for the following one. The step never becomes `verified`, gains no `verified_at`, and a session resting on such results can only complete with outcome `user_reported`. This is what lets a screenshot-only guide reach the end of its plan without anything having been checked on screen, and it is why the summary must distinguish verified steps from reported ones.

Explicit same-state diagnostic exceptions: analyses/questions/transcription in paused or blocked use Operation without leaving that state; plan edits there invalidate approval and set checkpoint=awaiting_user_confirmation. Analysis/plan regeneration in awaiting_user_confirmation can enter analyzing and return awaiting_user_confirmation for answer-only results or plan_ready for a new plan. Answer-only analyses in awaiting_user_action use processing then return awaiting_user_action. No ordinary provider operation starts in terminal/stopping states. Cancel operation routes any affected nonterminal session to paused, even before Start; terminal operations cannot reopen sessions.

## Recovery and timing

User inactivity expiry: 30 minutes since last explicit user interaction (command, manual upload, confirmation, Check); provider completion, capture callbacks, SSE and heartbeat do not reset it. Explicit `paused` suspends inactivity expiry, but absolute session lifetime remains 24 hours from creation. Renewing permission does not extend absolute lifetime. Background expiry sweep ≤60 seconds; requests enforce exact deadline regardless of sweep.

LLM timeout: each provider attempt deadline 30 seconds; at most one retry after ~2-second jittered backoff, total Operation deadline 65 seconds. Retry only transient failures or one schema-repair attempt for nonunsafe malformed output; never retry unsafe output automatically and never exceed two total provider calls for one Operation. On exhaustion, `blocked` with checkpoint and “Try again or upload a clearer screenshot.” Verification mismatch: at most two revisions of the same step, then blocked; user may explicitly choose a new plan. CaptureIntent timeout 5 seconds; release resources and request manual screenshot. All timings remain bounded by earlier session/grant expiry.

Network loss locally pauses immediately; server observes heartbeat loss within 15 seconds, revokes lease and records paused. Retry stop/revoke idempotently when network returns. If local epoch differs from server, send priority pause/stop first, then fetch current state; never replay frames. Backend restart revokes all live leases, marks in-flight operations canceled and moves affected sessions to paused; outbox replay uses event IDs for deduplication. Durable checkpoints must survive a backend process restart.

App restart never reconstructs observation from persisted permissions. Claiming a controller on a second device revokes old controller and increments epoch before acknowledgment. Recovered sessions first display last instruction as historical/unverified-current; fresh evidence is required to trust current UI.

## Races and examples

Pause racing provider completion: pause commits epoch 8; result bound to epoch 7 is discarded without emitting a new instruction. Deletion racing upload: admission/commit rechecks tombstone and owner; no orphan image becomes visible. Duplicate Done reuses idempotency result and creates one claim. Stale plan approval returns 409, displays the new plan and does not start.

User: “That is incorrect.” Save feedback, invalidate pointer/instruction and current verification attempt; enter blocked with `incorrect_guidance` reason, revoke observation; ask for a new screenshot. A manual diagnostic operation may run in blocked/paused without leaving that state. Explicit Retry after correction selects the checkpoint, with fresh permission if requested.

## Dependencies and traceability

Depends on transactions, Operation/outbox/epoch storage and local capture gate; no agent can write transitions directly. D02 affects deployment recovery tests, D05 time budgets. SEC-03/05/12/13 apply. R09–R13/R20/R22 → F09–F13/F20/F22 → T09–T13/T20/T22/T32/T33; [17](17-traceability-matrix.md) maps all requirements. No unresolved enum names or transition routes are left to implementation.
