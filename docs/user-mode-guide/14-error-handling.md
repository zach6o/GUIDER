# 14 · Error handling and recovery

Status: proposed MVP. State authority: [05](05-session-state-machine.md). Every failure below defines user message, recovery, logging, retry and safety behavior. Error codes are stable categories; user text may be localized without exposing internal errors.

## Global recovery rules

Local safety actions take priority over network/model completion. Remove stale pointers immediately. Preserve only a safe stable checkpoint; a recoverable error normally enters `blocked` or `paused`, not terminal `failed`. No retries may execute user actions, grant consent, reuse expired evidence or claim success. New context is not permission to unblock a prohibited task.

Retry profiles: `N` none automatic; user can correct context. `P` provider transient retry once after ~2 seconds jitter, 30-second deadline per attempt, then blocked. `C` capture waits at most 5 seconds, closes handles, offers manual screenshot; one new user-triggered attempt only. `B` network reconnect 1,2,4,8,16,30 seconds with jitter, capped at 30; no media replay, user Resume required. `R` reconciler retries metadata cleanup 3 times with 1/5/30-second delays then durable background job/alert; capture already closed. Verification permits two revised attempts then blocked, not infinite retry. Retention purge retries persist until successful and alert when SLO missed; they cannot silently abandon data.

Logging profiles: `L` request/session/operation IDs, error code, app key, versions, duration, retry count; never image/OCR/transcript/title/full URL/token. `S` L plus content-free SafetyEvent with rule/reason/epoch. `M` L plus media metadata and deletion result. A user report text is private content with normal retention, not log content.

| Failure / code | User-facing message | Recovery/state | Log | Retry | Safety behavior |
|---|---|---|---|---|---|
| Unclear screenshot / image_unreadable | “I can't read the relevant area. Please crop it more closely.” | Keep checkpoint, request clearer image, operation fails/inconclusive | M | N | No guessed pointer or step pass |
| Wrong application / wrong_application | “This is a different application from the current step.” | Block; select correct supported app or revise plan | S | N | Revoke scope, new local permission |
| Screen permission denied / permission_denied | “You can continue by uploading screenshots.” | Await choice; Start screenshot_only activates without grant | S | N | Never re-prompt in loop or capture anyway |
| Screen permission revoked / permission_revoked | “Observation is off. Choose Resume or upload an image.” | Paused with checkpoint | S | N | Close local gate, invalidate epoch/lease/pointer |
| User performs different action / unexpected_action | “The screen changed differently than expected. Let's check where you are.” | Mismatch; ask fresh context, revise current instruction | L | N | No assumption of intended action or success |
| UI changed / ui_changed | “That control may have moved. Please share the current panel.” | Invalidate instruction location, request context | L | N | No stale coordinate reuse |
| Window moved/resized / geometry_changed | “The window moved. Choose Check again to place the marker.” | Keep text, recapture after user Check | L | C | Hide pointer on geometry generation change |
| Multiple monitors / mapping_ambiguous | “I can't safely place a marker here. Use the screenshot view.” | Image-viewer fallback; reselect window if desired | L | N | Never project to wrong monitor; no full-screen capture |
| Application crash / target_unavailable | “The selected application closed. Reopen it when you're ready.” | Paused/blocked; user reopens, reviews checkpoint | S | N | Release selected handle; new grant |
| Network loss / network_unavailable | “Offline — observation is off. Your last instruction is still available.” | Paused; reconnect then review/resume | S | B | Drop queued frames/audio; server lease expires ≤15 s |
| LLM timeout / provider_timeout | “The check took too long. Try again or provide a clearer screenshot.” | Retry once then blocked | L | P | No unverified result; cancel/discard old operation |
| Vision failure / vision_failed | “I couldn't identify the relevant control.” | Request crop/text; blocked if repeated | M | P only transient service error | Invalid/suspicious output gets no automatic retry; no pointer |
| Voice transcription failure / audio_unintelligible | “I couldn't understand that. Try again or type your request.” | Composer remains; no command created | M | N | Mic off, clip purged at deadline, no guessed command |
| Incompatible Windows / platform_unsupported | “Live Guide isn't available on this Windows setup. Use screenshot help.” | Web/manual mode, explain tested support | L | N | No API bypass or elevated capture fallback |
| Unsupported application / app_not_allowed | “Live guidance for this application is not supported yet.” | Block live; allow safe sanitized explanation if within supported task | S | N | Cannot add allowlist entry from model/user text |
| Unsafe task / unsafe_task | “Guide can't assist with this action. You can return to a supported task.” | Block with reason; offer safe general alternative | S | N | Revoke capture; confirmation cannot unlock blocked task |
| User stuck / repeated_mismatch | “Let's try another approach. Show the current result or review the plan.” | After two revisions blocked; user chooses new approach | L | N | No repeated command loop or escalating risk |
| Verification mismatch / verification_mismatch | “The result does not match this step yet.” | Save mismatch, ask focused evidence/revised step | L | N | No next-step advance or achieved badge |
| Incorrect AI guidance / incorrect_guidance | “Thanks for the correction. I'll recheck before suggesting another step.” | Feedback, blocked, invalidate instruction and ask new screenshot | S | N | Revoke grant, cancel pending verification; don't defend stale answer |
| Session expiry / session_expired | “This session expired. Review the task to start a new session.” | Expired; create successor with fresh plan confirmation | S | N | No restored consent, stale token or cached pointer |
| Client crash / client_interrupted | “Your last session was interrupted. Review before continuing.” | Server watchdog pauses; relaunch recovery review | S | N | No surviving capture service; new controller/permission |
| Backend restart / server_restarted | “The connection restarted. Observation is off.” | Reconcile queued work, pause affected sessions | S | R for metadata | Revoke leases, reject prior epoch results, replay events safely |
| Token expiry/revocation / token_expired | “Sign in again to continue. Observation is off.” | Pause; refresh or sign-in, then review Resume | S | One refresh; then N | Close capture before refresh; no unauthenticated media |
| Image deleted/expired during work / evidence_unavailable | “That image is no longer available. Upload a new one to recheck.” | Cancel dependent operation, scrub derived data | M | N | Tombstone wins over late result; no reappearance |
| Rate/budget limit / rate_limited | “You've reached the current limit. Try again after [time].” | Keep safe explanation, display Retry-After | L | N until deadline | Stop/Pause still work; no alternate-provider bypass |
| Stale state / stale_version | “This session changed elsewhere. Review the latest step.” | Fetch state, discard queued ordinary mutation | L | One GET then N | Priority Stop/Pause still accepted |
| Device/controller loss / controller_lost | “This session is active on another device. Observation is off here.” | Pause former controller, review transfer | S | N | Old credential/epoch cannot capture |
| Sensitive content / redaction_required | “Hide private information before sharing this image.” | Local preview/mask or choose another window | S/M | N | No raw image sent for detection; purge accidentally received media |
| Storage/purge failure / deletion_delayed | “Your data is unavailable for use; deletion is still processing.” | Receipt pending, lifecycle worker retries and alerts | S | Durable retry until purge | No read resurrection; do not falsely show purged |
| Invalid provider output / output_rejected | “I couldn't produce a reliable next step. Please share more context.” | Validate failure; blocked/manual alternative | S if unsafe, otherwise L | One schema repair only for nonunsafe malformed output | No raw unsafe output rendered or executed |

## Restart and conflict details

Backend restart never resumes in-flight screen processing automatically with old authorization. Reconciler distinguishes queued-not-sent versus sent-unknown provider work; sent-unknown is canceled unless provider idempotency is proven. Session event/outbox commits are atomic; clients fetch snapshot after replay gap. Terminal Stop must finish summary cleanup within 5 seconds under normal backend health; if storage unavailable, local stop and lease revocation still prevent capture, and durable retry finishes later.

A replacement screenshot or incorrect-guidance report during processing increments operation generation/epoch as needed, invalidates old evidence references, and prevents old output publication. Manual analysis while paused stays paused. Completing a task while mandatory steps are blocked returns verification_required/policy_blocked rather than silently skipping.

Example: network disconnect occurs during a user-triggered recheck. Native drops queued image, hides marker and shows last instruction as not rechecked. Even after reconnection succeeds, it does not upload the old frame or reopen capture. User reviews and grants new permission, or chooses manual screenshots.

## Dependencies, assumptions, decisions and traceability

Assume errors can occur between any two commits; fault injection tests must cover those boundaries. Depends on 05/07/08/09 and native disposal behavior. D01/D02/D05 tune provider and operational targets, never safety semantics. SEC-03/05/12/13/14 apply. R10–R13/R20/R22/R23 → F10–F13/F20/F22/F23 → T10–T13/T20/T22/T23/T31–T37 in [17](17-traceability-matrix.md).
