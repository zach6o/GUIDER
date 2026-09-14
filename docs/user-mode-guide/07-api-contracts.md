# 07 · API contracts

## Implemented local development connector

[ADR-015](adr/015-browser-observation-and-personal-cloud.md) adds a separate `/api/v1/local-guide` prefix. These routes require a loopback client, a localhost Host and an exact configured local browser Origin. They never expose saved task/account resources. Success bodies are returned directly; errors use the existing error envelope. Generated schemas in [`openapi.json`](../../user-mode/contracts/openapi.json) cover the implemented surface.

| Method/path under `/api/v1/local-guide` | Request and response |
|---|---|
| `POST /connection` | `{api_key, model, accepted_cloud_terms:true}`; returns `{connection_token, model, expires_in_seconds:1800}` after model access validation |
| `POST /checks` | Capability Bearer token; `{goal, question, previous_step, image_base64, reviewed:true}`; returns `{observation, next_step, where, check_for, question, disposition}` |
| `POST /cancel` | Capability Bearer token; cancels pending check and invalidates its result; 204 |
| `DELETE /connection` | Capability Bearer token; idempotently cancels work and clears the in-memory key; 204 |

Models are `gpt-4.1-mini` and `gpt-4.1`. Dispositions are `guide`, `needs_context` and `blocked`; non-guide responses have empty action fields, and blocked responses stop browser sharing. Check requests have a 6 MiB JSON transport bound, 4 MiB image bound and 2,560px edge bound. One check may run at a time, at least two seconds apart, with at most 40 checks per connection. Keys, frames and answers are not persisted by this connector. The account contracts below retain their separate Supabase authentication and envelope rules.

## Account API target

Status: proposed v1 contracts, not existing routes. Prefix **`/api/v1/guide`** applies to every route below. This file is the route and wire-schema authority. Generate OpenAPI 3.1 plus shared JSON Schemas from these contracts in phase 0/1; generation is an implementation task, not claimed complete here.

## Shared transport rules

JSON requests/responses use UTF-8, snake_case, UTC RFC3339 timestamps, UUID identifiers, finite numbers and strict additional-property rejection. Required fields are unmarked; `?` means optional and omitted, not arbitrary null. Explicit nullable fields are marked `|null`. All examples using `<uuid>` are explanatory placeholders, not test-valid UUIDs. Maximum JSON body 64 KiB, text fields independently bounded below. All routes require `Authorization: Bearer <Supabase access JWT>`; never accept tokens in URLs. All resources must belong to verified `sub`; return 404 for nonexistent or foreign IDs. Device actions also require `X-Guide-Device-Id` and its opaque device credential; credential alone is insufficient without JWT.

Success envelope: `{data:T, request_id:uuid}`. Collections: `T={items:[Item], next_cursor:string|null}`. Error envelope, used by **every endpoint**:

```json
{"error":{"code":"stale_version","message":"The session changed. Reload before continuing.","retryable":false,"details":{"current_version":8}},"request_id":"b442d01e-7c78-4fa6-b80f-c1cb386dc2a6"}
```

Common errors on all routes: 400 `invalid_request`; 401 `invalid_token|token_expired`; 403 `device_revoked|policy_blocked`; 404 `not_found`; 409 `stale_version|invalid_transition|idempotency_conflict|operation_in_progress`; 410 `data_deleted|session_expired`; 413 `payload_too_large`; 415 `unsupported_media_type`; 422 `validation_failed`; 429 `rate_limited` with Retry-After; 503 `dependency_unavailable`. Never expose stack traces, SQL, prompts or another user's existence. Endpoint-specific errors below supplement these common errors, not replace them.

ErrorBody fields: `code:string[1..80]`, `message:string[1..500]`, `retryable:boolean`, `details?:{current_version?:int,retry_after_seconds?:int,field_errors?:[{field:string,code:string}]}`. No arbitrary details object or echoed user values. Async Operation failures use this same inner schema; transport acceptance is not operation success.

### Authentication/authorization profiles

| Profile | Required checks |
|---|---|
| U | Valid Supabase JWT, active User, owner of every referenced ID; cross-ID task/session/step/evidence consistency |
| C | U plus registered non-revoked device credential and current controller binding for native commands |
| O | C plus current local grant record, consent nonce, selected app scope, control epoch and live capture lease |

Manual web/session commands use U; native ones use C. A web user may always pause/stop/revoke their own session, even if a native device controls it. Web cannot grant observation or submit `source=observation`.

### Idempotency, concurrency and audit profiles

`I`: POST/PATCH mutation requests require `Idempotency-Key` UUID except the explicitly exempt lease heartbeat. Scope = user + method + canonical route + key. Store request digest and original status/response for 24 h; same request returns original result, different content returns 409. Recheck auth/ownership/tombstone before replay; deletion replaces replay body with 410. Multipart digest includes bytes and metadata. `R`: GET is read-only/repeatable. `D`: DELETE is idempotent; repeat returns same deletion job or already-purged receipt, not resurrected data. `P`: priority pause/stop/revoke accepts stale version; always applies restrictive action. Other existing-session mutations require `expected_version:int>=1` and exact compare-and-swap; successful async admission returns updated session version. Resource deletion needs no session version. Create task/device have no prior version.

Audit `A`: immutable content-free event `{actor_id,device_id?,action,resource_type,resource_id,result,reason_code,request_id,at}`. Audit `S`: A plus policy/consent version, scope hash, control epoch or confirmation challenge ID; no screen content. Audit `M`: A plus media ID, byte count, type and expiry, no filename/OCR. Audit `Q`: reads record route category, authorization result and request ID; media reads/deletion receipts also record resource access. Every authorization denial is audited; sensitive payloads never are.

### Rate profiles (rolling windows, authenticated user aggregate)

| Profile | Ceiling | Additional controls |
|---|---|---|
| Read | 120/min | History max 50/page, 10/min media-content reads |
| Write | 60/min | Create task/session max 10/hour; one nonterminal session per task |
| AI | 10/min, 100/day | One in-flight AI/media operation/session, max 3 evidence images and 12 plan steps |
| Image | 30/min, 100/hour | ≥2 s between observed frames; 10 MiB/image; 20 retained/task |
| Voice | 10/min, 60/hour | 30 s/5 MiB audio; one transcript operation/session |
| Safety | Dedicated capacity | Restrictive requests never denied because normal user quota is depleted; coalesce duplicates; edge DoS protection remains and local stop always works |
| Events | 2 open streams/user | 1 stream/client, reconnect exponential backoff 1–30 s |
| Delete | 10/hour | Repeats reuse job; account deletion one active job/user |

Additionally cap unauthenticated failures at 30/min/IP and total ingress at 300/min/IP with deployment-aware trusted proxy parsing; do not rate-limit a shared enterprise IP as if it were an owner. Provider token budget: max 8,000 input text tokens and 2,000 output tokens per call, media bounded separately, max 40 provider calls/session. Exhaustion returns 429 `session_budget_exhausted` and screenshot/manual explanatory fallback without another provider call.

Capture intent reserves one Image quota unit; its matching upload consumes the reservation, not a second unit. Failed/expired intents release the reservation after their deadline, while repeated abuse remains subject to ingress limits. Idempotent retries are not new provider/media budget charges. Voice accepts only WAV PCM16 mono (16/24/48 kHz) or WebM Opus, ≤5 MiB and ≤30 seconds; normalizes to mono 16 kHz PCM under SEC-04. Screen and audio consent remain separate.

## Canonical response schemas

| Schema | Fields |
|---|---|
| Task | `id:uuid, title:string, goal:string, category:Category, application_key:string, status:TaskStatus, current_session_id:uuid\|null, created_at:time, updated_at:time` |
| Session | `id, task_id, previous_session_id:uuid\|null, state:SessionState, state_version:int, control_epoch:int, current_step_id:uuid\|null, confirmed_plan_version:int\|null, observation_mode:screenshot_only\|window, controller_device_id:uuid\|null, outcome:Outcome\|null, checkpoint_state:SessionState\|null, expires_at:time, last_user_activity_at:time, created_at, updated_at` |
| Screenshot | `id, task_id, session_id:uuid\|null, source:manual\|observation, version:int, status:MediaStatus, width:int, height:int, content_type:string, byte_size:int, captured_at:time, expires_at:time, replaces_screenshot_id:uuid\|null` |
| Analysis | `id:uuid, screenshot_ids:[uuid], observations:[{label:string,bbox:BBox\|null,confidence:number}], explanation:string, needs_context:boolean, context_request:string\|null` |
| Plan | `id:uuid, task_id, session_id, version:int, status:draft\|confirmed\|superseded, steps:[PlanStep], assumptions:[string], created_at:time` |
| PlanStep | `id:uuid, ordinal:int, title:string<=120, action:string<=1000, application_key:string, risk:low\|medium\|high, success_criterion:string<=500, evidence_kind:visual\|text\|self_report, required:boolean` |
| Instruction | `id:uuid, session_id, step_id, version:int, what:string<=1000, where:string<=300, why:string\|null<=500, confirmation_hint:string<=300, cannot_find_hint:string<=300, evidence_ids:[uuid], pointer:Pointer\|null, action_confirmation_id:uuid\|null, status:ready\|superseded\|invalidated` |
| Pointer | `screenshot_id:uuid, screenshot_version:int, bbox:BBox, label:string<=120, confidence:number, expires_at:time`; BBox normalized as 03 |
| Command | `id:uuid, session_id, source:text\|voice, text:string<=4000, intent:ask\|next\|repeat\|stuck\|incorrect\|pause\|resume\|stop, status:accepted\|processed\|rejected, created_at:time` |
| Verification | `id:uuid, session_id, step_id, status:pending\|passed\|mismatch\|inconclusive\|user_reported\|canceled, evidence_ids:[uuid], reason:string<=1000, verifier_kind:visual\|text\|self_report, evidence_available:boolean, created_at:time` |
| Permission | `id:uuid, session_id, device_id, status:requested\|granted\|denied\|revoked\|expired, app_key:string, scope:window, crop:BBox\|null, control_epoch:int, consent_version:string, expires_at:time\|null, lease_expires_at:time\|null` |
| CaptureIntent | `id:uuid, session_id:uuid, permission_id:uuid, intent:context\|verify, step_id:uuid\|null, claim_id:uuid\|null, control_epoch:int, status:requested\|received\|canceled\|expired, expires_at:time` |
| ActionChallenge | `id:uuid, action:string, target_summary:string<=500, consequence:string<=500, instruction_version:int, expires_at:time, status:pending\|confirmed\|declined\|expired\|consumed` |
| Operation | `id:uuid, kind:analyze\|plan\|instruction\|verify\|transcribe\|delete, status:queued\|running\|succeeded\|failed\|canceled, session_id:uuid\|null, result:Analysis\|Plan\|Instruction\|Verification\|Transcript\|DeletionReceipt\|null, error:ErrorBody\|null, created_at:time, updated_at:time` |
| Pending | `operation_id:uuid, session:Session\|null, poll_after_ms:int` (202 response) |
| Transcript | `voice_input_id:uuid, text:string<=4000, language:string, confidence:number\|null, status:ready\|failed, expires_at:time` |
| Summary | `session_id, outcome:Outcome, verified_steps:[uuid], unverified_steps:[uuid], corrections:[string], text:string<=4000, next_action:string\|null, created_at:time` |
| DeletionReceipt | `id:uuid, scope:screenshot\|session\|task\|account, status:queued\|purging\|purged\|failed, requested_at:time, online_purge_due_at:time, backup_expiry_due_at:time\|null, completed_at:time\|null` |

`Category`, `SessionState`, `TaskStatus`, `MediaStatus`, `Outcome` and all entity persistence fields are fixed in 08; API response schemas intentionally omit internal object keys/tokens. Enum changes require contract review. `ErrorBody` is the inner common error object. ID/time shorthand uses UUID/RFC3339; all shown response fields are required, nullable only where marked. MVP objective verification uses fresh screenshot evidence; user-typed output is context/self-report, not independent proof. `evidence_kind=text` and `verifier_kind=text` are reserved for a later authenticated evidence-source adapter and are rejected for MVP plans/results.

## Endpoint contracts

Each row defines method/route, auth profile, **complete endpoint-specific request**, response/status, idempotency/rate/audit profiles and additional errors. Common headers/schema/error rules above apply to every row. `V` expands to required `expected_version:int`; `E` to optional `evidence_ids:[uuid]` max 3. Empty request means no fields other than explicitly shown. All routes below are relative to the prefix.

| Method and route | Auth | Request | Response | Policy / additional errors |
|---|---|---|---|---|
| POST `/tasks` | U | `{goal:string[1..4000],title?:string<=120,category:Category,application_key:string<=80}` | 201 `{task:Task,session:Session}` | I/Write/A; `unsupported_category` 422 |
| GET `/tasks/{task_id}` | U | No body | 200 Task | R/Read/Q |
| POST `/tasks/{task_id}/screenshots` | U; O for observation | Multipart `file`, `metadata` JSON `{session_id?:uuid,source:manual\|observation,purpose:context\|verification\|error\|disagreement,captured_at:time,replaces_screenshot_id?:uuid,expected_version?:int,permission_id?:uuid,control_epoch?:int,capture_generation?:int,capture_intent_id?:uuid}`. Session version required if session_id supplied; observation requires all capture fields and session_id | 201 `{screenshot:Screenshot,session:Session\|null,operation_id:uuid\|null}` | I/Image/M; 422 `image_unreadable\|redaction_required`, 403 `capture_not_permitted`, 409 `stale_capture` |
| GET `/screenshots/{screenshot_id}/content` | U | No body | 200 redacted binary with Content-Type, no JSON; `Cache-Control:no-store` | R/Read/M; 410 `media_expired` |
| DELETE `/screenshots/{screenshot_id}` | U | No body | 202 DeletionReceipt | D/Delete/M; immediately inaccessible |
| POST `/tasks/{task_id}/analyses` | U | `{session_id:uuid,V,screenshot_ids:[uuid][1..3],question:string[1..4000]}` | 202 Pending → Analysis | I/AI/M; 422 `needs_context` when no usable media |
| POST `/tasks/{task_id}/plans` | U | `{session_id:uuid,V,evidence_ids?:[uuid],constraints?:string<=2000}` | 202 Pending → Plan | I/AI/A; 403 `unsafe_task` |
| PATCH `/tasks/{task_id}/plans/{plan_version}` | U | `{session_id:uuid,V,steps:[PlanStepInput][1..12]}`; PlanStepInput = PlanStep excluding id, with `id?:uuid` for retained steps | 200 `{plan:Plan,session:Session}` | I/Write/A; validates risk server-side; 409 `plan_superseded` |
| POST `/tasks/{task_id}/plans/{plan_version}/confirmations` | U | `{session_id:uuid,V,accepted:true}` | 200 `{plan:Plan,session:Session}` | I/Write/S; 409 `plan_superseded` |
| POST `/sessions/{session_id}/start` | U or C live | `{V,plan_version:int,mode:screenshot_only\|window,device_id?:uuid}`; device required for window | 200 Session | I/Write/S; 409 `plan_unconfirmed`; live returns awaiting_screen_permission |
| POST `/sessions/{session_id}/permissions` | C | `{V,app_key:string,scope:window,crop?:BBox,consent_version:string}` | 201 `{permission:Permission,consent_nonce:string,session:Session}` | I/Write/S; nonce single-use, 60 s; 403 `app_not_allowed`; records request only |
| POST `/sessions/{session_id}/permissions/{permission_id}/decisions` | C | `{V,decision:granted\|denied,consent_nonce:string,scope_fingerprint:string<=128}` | 200 `{permission:Permission,session:Session}` | I/Write/S; 409 `consent_stale`; only native local user/OS result; fingerprint contains no title/path |
| DELETE `/sessions/{session_id}/permissions/{permission_id}` | U or C | No body | 200 `{permission:Permission,session:Session}` | D+P/Safety/S; pauses session and increments epoch |
| POST `/sessions/{session_id}/heartbeat` | C | `{control_epoch:int,permission_id:uuid}` | 200 `{lease_expires_at:time,session:Session}` | Repeatable renewal, no idempotency key/expected_version; Safety/S; 409 `lease_lost`; never renews grant expiry |
| POST `/sessions/{session_id}/captures` | O | `{V,permission_id:uuid,control_epoch:int,intent:context\|verify,step_id?:uuid,claim_id?:uuid}`; verify requires current step and completion claim | 201 `{capture:CaptureIntent,session:Session}` | I/Image/S; 409 `stale_capture\|capture_in_progress`; intent expires after 5s, consumed by one matching screenshot upload |
| POST `/sessions/{session_id}/commands` | U or C | `{V,text:string[1..4000],intent:Command.intent,source:text\|voice,voice_input_id?:uuid}` | 202 `{command:Command,operation_id:uuid\|null,session:Session}` | I/Write/A plus AI if dispatched; voice_input_id required for voice; pause/stop intents have P/Safety priority |
| POST `/sessions/{session_id}/voice-inputs` | U or C | Multipart `file`, metadata `{V,language:en,consent_version:string}` | 202 Pending → Transcript | I/Voice/M; 422 `audio_unintelligible`; transcription never implicitly submits command |
| POST `/sessions/{session_id}/screenshots` | U or O | Same screenshot multipart schema except task/session IDs inferred from route; `expected_version` required | 201 `{screenshot:Screenshot,session:Session,operation_id:uuid\|null}` | I/Image/M; same errors/rules as task screenshot route; explicit during-session alias |
| GET `/sessions/{session_id}/instructions/current` | U | No body | 200 `{instruction:Instruction\|null,action_challenge:ActionChallenge\|null,session:Session}` | R/Read/Q; no side effects or hidden generation; Cache-Control:no-store |
| POST `/sessions/{session_id}/instructions` | U or C | `{V,E,reason:initial\|recheck\|retry}` | 202 Pending → Instruction | I/AI/A; 409 `step_not_verified` for attempts to skip ahead |
| POST `/sessions/{session_id}/steps/{step_id}/completion-claims` | U or C | `{V,statement:string<=1000}` | 201 `{claim_id:uuid,step_id:uuid,status:user_claimed,session:Session}` | I/Write/A; no pass implied |
| POST `/sessions/{session_id}/steps/{step_id}/verifications` | U or C | `{V,claim_id:uuid,evidence_ids:[uuid],self_report?:string<=1000}`; nonempty evidence OR self_report required | 202 Pending → Verification | I/AI/A; 422 `evidence_required`, 409 `evidence_stale` |
| POST `/sessions/{session_id}/pause` | U or C | `{expected_version?:int,reason:user\|network\|auth\|lock\|suspend\|controller_lost}` | 200 Session | I+P/Safety/S |
| POST `/sessions/{session_id}/resume` | U or C | `{V?,mode:screenshot_only\|window,checkpoint_reviewed:true,device_id?:uuid}` | 200 `{session:Session,next_operation_id?:uuid}` | I/Write/S; 409 `context_review_required\|plan_unconfirmed\|invalid_transition`; 410 for terminal/expired. Resumes from `paused` or `blocked` only, to the recorded checkpoint; `mode:window` returns to `awaiting_screen_permission` because no grant is restored; a withdrawn instruction is re-requested and its Operation returned |
| POST `/sessions/{session_id}/stop` | U or C | `{expected_version?:int,reason:user\|close\|sign_out\|emergency}` | 200 Session (stopping or completed) | I+P/Safety/S; terminal repeated stop returns existing terminal session unchanged |
| POST `/sessions/{session_id}/steps/{step_id}/retries` | U or C | `{V,reason:string<=1000}` | 202 Pending → Instruction | I/AI/A; 409 `retry_limit\|blocked_task\|invalid_transition`; only the step the session is on, only from `awaiting_user_action`; counts one attempt, so it feeds the stuck detector and is refused after three; changes no step status. Evidence (`E`) arrives with the evidence path |
| POST `/sessions/{session_id}/feedback` | U | `{V?,step_id?:uuid,instruction_id?:uuid,kind:incorrect_guidance\|helpful\|unhelpful\|privacy_concern,text?:string<=2000}` | 201 `{feedback_id:uuid,session:Session,step?:Step,verification_withdrawn:bool}` | I/Write/S for incorrect/privacy, otherwise A; `incorrect_guidance` requires `step_id` and returns 422 `validation_failed` without one, invalidates the pointer, downgrades a `passed` visual result for that step to `mismatch` with the step back to `pending`, revokes observation and blocks. `evidence_ids` arrives with the evidence path |
| GET `/sessions` | U | Query `cursor?:opaque,limit?:int[1..50]=20,task_id?:uuid,state?:SessionState` | 200 collection of `{session:Session,task_title:string}` | R/Read/Q; cursor scoped to owner and filters |
| GET `/sessions/{session_id}` | U | No body | 200 Session | R/Read/Q |
| POST `/tasks/{task_id}/sessions` | U | `{previous_session_id:uuid,mode:restart\|continue}` | 201 Session in task_created | I/Write/A; prior must be terminal, 409 `session_already_active`; copies redacted goal/context only, requires new plan confirmation |
| POST `/sessions/{session_id}/completion` | U | `{V,outcome:achieved\|user_reported,self_report?:string<=1000}` | 200 `{session:Session,summary:Summary}` | I/Write/A; 409 `verification_required` for unverified achieved; required risky/blocked steps cannot be bypassed |
| GET `/sessions/{session_id}/summary` | U | No body | 200 Summary | R/Read/Q; 409 `session_not_terminal` |
| DELETE `/sessions/{session_id}` | U | No body | 202 DeletionReceipt | D+P/Delete/S; stops session first, deletes session-scoped evidence/context; task may remain |
| DELETE `/tasks/{task_id}` | U | No body | 202 DeletionReceipt | D+P/Delete/S; includes task-level screenshots and all sessions |
| GET `/operations/{operation_id}` | U | No body | 200 Operation | R/Read/Q; verifies owner through stored operation, not only session |
| DELETE `/operations/{operation_id}` | U or C | No body | 200 `{operation:Operation,session:Session\|null}` | D+P/Safety/S; cancels provider/media work, purges pending clip, pauses nonterminal parent session and invalidates epoch; terminal result remains terminal |
| GET `/deletions/{deletion_id}` | U | No body | 200 DeletionReceipt | R/Read/Q; account receipt available until auth erased, shown before final sign-out |
| GET `/sessions/{session_id}/events` | U or C | Headers Authorization, optional Last-Event-ID; no body | 200 SSE | R/Events/Q; 409 `event_cursor_expired` requires GET session |
| POST `/devices` | U | `{name:string<=80,platform:windows,client_version:string<=40,installation_nonce:uuid}` | 201 `{device_id:uuid,device_credential:string,created_at:time}` | I/Write/S; credential returned once except protected idempotent retry; max 5 active devices/user |
| GET `/devices` | U | No body | 200 collection `{id:uuid,name:string,status:active\|revoked,last_seen_at:time}` | R/Read/Q |
| DELETE `/devices/{device_id}` | U | No body | 200 `{device_id:uuid,status:revoked}` | D+P/Safety/S; pause sessions/controller epoch increment |
| POST `/sessions/{session_id}/controller` | C | `{V,device_id:uuid,transfer_confirmed:true}` | 200 Session in paused | I/Write/S; matching authenticated device; old controller revoked |
| POST `/sessions/{session_id}/steps/{step_id}/action-confirmations` | U or C | `{V,instruction_version:int,decision:confirmed\|declined,challenge_id:uuid}` | 200 `{id:uuid,status:consumed\|declined,session:Session}` | I/Write/S; 403 `action_blocked`, 409 `challenge_stale`; voice cannot invoke; confirmed challenge is consumed atomically |
| DELETE `/account` | U | Header `X-Confirm-Deletion: delete-my-guide-account`; no body; reauthentication ≤5 min required | 202 DeletionReceipt | D+P/Delete/S; 403 `recent_auth_required`; blocks account immediately, erases Guide data then Supabase identity |

Action challenges are created by the server safety gate and returned as `action_confirmation_id` on a safe preparatory Instruction, with `action_challenge` on GET current (null when absent). Challenge ID is the ActionConfirmation entity ID. Its `instruction_version` is the reserved version of the exact pending final instruction, not the preparatory instruction's version. Confirmation atomically publishes that stored final instruction version and consumes the challenge; it does not regenerate different content. Challenge expires after 5 minutes, binds session/step/plan/target/pending instruction version, and cannot be reused. Any change to the pending action invalidates it. GET current then returns the published instruction; no external action is executed.

Observed capture admission: native POST captures records a user-triggered intent and moves session to capturing. The response/`capture.requested` event carries the same intent ID; event replay cannot create another capture. Native acquires one frame and uploads with that ID and returned session version. Server validates single use/5-second deadline/epoch/permission and schedules one instruction operation for context, or verification operation for verify; upload returns operation_id. Manual upload returns operation_id=null and waits for explicit analyses/instructions/verifications request. Recheck without a completion claim can request context but cannot produce a passed verification. Initial live context requires an explicit Start/Check gesture; no backend timer requests capture.

Allowed operations while paused/blocked: manual image upload, analyses, ordinary question/transcription, feedback, deletion, Stop and explicit Resume/Retry. They preserve paused/blocked state until explicit recovery. Plan generation/edit in paused stores a proposed version and changes checkpoint to awaiting_user_confirmation without resuming; live permission stays revoked. Before start, analyses/plan operations are allowed in task_created/awaiting_user_confirmation; in awaiting_user_action an analysis is answer-only unless user explicitly requests revision. Other operation/state pairs follow 05 and return invalid_transition when absent. Idempotent replay after epoch change returns the original receipt with current session obtainable by GET; clients must not render receipt data as a current instruction.

## Streaming and ordering

SSE is required for progress, processing state and instruction-ready notifications in live Windows sessions. Screenshot-only web can poll Operations and GET current instruction every ≥2 seconds. Use authenticated fetch streaming in web because native EventSource cannot set bearer headers; never put tokens in query strings. No WebSocket is required. Assistant explanation text may stream post-MVP; MVP delivers whole validated messages. Voice transcription is batch in MVP. Instruction updates are atomic complete objects or IDs to fetch, never partial unsafe instructions.

Event wire shape: `id:<session_uuid>:<sequence>`; `event:<type>`; `data:{event_id,session_id,sequence,state_version,control_epoch,type,at,payload}`. Types are enumerated in 05 plus `operation.completed`, `operation.failed`, `instruction.invalidated`, `permission.granted`, `permission.denied`, `data.deletion_requested`. Payload contains resource IDs/status, never images/secrets/raw text. Heartbeat comments every 15 seconds do not count as user activity. Retain replay events 7 days; replay ordered by sequence, client deduplicates and ignores lower epochs. A sequence gap triggers authoritative GET. Reauthorize at connection, every 15 seconds and token expiry; close on revocation/expiry. Events are notification, not permission to capture.

## Example sequence and dependencies

Python screenshot help: POST tasks → POST task screenshots → POST analyses → poll operation → show Analysis boxes in viewer. Planning: POST plans → edit if needed → POST plan confirmations → POST session start with screenshot_only → POST instructions → GET current → POST completion-claims → upload fresh screenshot → POST verifications. Repeating the same idempotency key cannot create a second task or verification.

Assumes authoritative ownership and PostgreSQL transactions. D01/D02 set providers and deployment, not routes. Security SEC-01–SEC-16; tests T03–T06/T09–T20/T23/T28/T29/T32/T33/T34/T35/T36/T37. Traceability [17](17-traceability-matrix.md). All APIs are proposed; no legacy alias or deprecation has been invented.
