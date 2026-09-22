# Personal browser guidance readiness

Reviewed 2026-09-22. Selected scope: **browser screen guidance with your own API
key**, running on this Windows PC. This checklist supplements the full release
checklist in [23](23-completion-checklist.md); it does not mark the public or
native product complete.

## Assessment

The local browser workflow is implemented: connect a personal provider key,
choose a window, capture a still, crop/hide private information, explicitly send
the reviewed image, receive one next step, and check again after acting.
It needs final live-provider and real browser-picker verification before being
called verified for everyday use. Automated provider answers and capture sources
are simulated, even when the actual application logic is exercised.

The demo is a separate practice exercise. Its moving hints do not identify
controls in your real applications. Personal AI guidance currently returns text
beside the reviewed screenshot; it is not a native pointer over other windows.

## Essential personal-use checklist

- [x] Local web/backend launcher, locked dependencies and database migrations exist.
- [x] Start the launcher on this PC and verify HTTP 200 from the web app and API,
  including the personal-connection route in the API contract.
- [x] Window preview, still-image review, crop/hide, follow-up questions,
  cancellation, stop and key disconnect are implemented.
- [x] Fix default Claude availability. The UI offered Claude, but the default
  registry only exposed OpenAI for personal guidance. Claude now registers for
  the personal guide role without requiring a saved-account backend key.
  Unconfigured saved-task roles continue to use the labeled fixture.
- [x] Correct provider disclosures. The entry is now **AI screen guide**, and
  review text, send button, progress, answer image description and retention
  notice identify the selected service. Previously these said OpenAI for Claude.
- [x] Add regression coverage for a default Claude connection through the real
  local API with simulated provider transport, and its browser review/send flow.
- [ ] Connect your chosen provider using your own API key in the app. Confirm the
  offered model is accessible to that account. Do not put the key in chat or a
  frontend environment file. No real credential was exercised in this review.
- [ ] Test the actual Chrome/Edge window picker: grant access, cancel it, change
  the source, close the source and use the browser's stop-sharing control.
  Automated capture tests substitute a synthetic video stream.
- [ ] Complete one real, nonsensitive task through at least three reviewed
  frames. Confirm that guidance matches the screen, a follow-up changes the
  answer appropriately, and the final result can be checked independently.
- [ ] Verify live failure handling for the chosen account: rejected/revoked key,
  unavailable model, quota exhaustion and interrupted request. Automated error
  tests exist; live account behavior remains unverified.
- [ ] Check actual latency and account usage for that trial and choose an
  acceptable personal usage budget. The connector limits calls, but does not
  enforce a currency-denominated spend cap.

The last five items are the acceptance work for the selected personal workflow.
They do not require building the saved-account or native products first.

## Start and use it

In PowerShell at the repository root:

```powershell
# Dependencies are already present on the reviewed PC.
# On a fresh checkout, first run: npm.cmd install
npm.cmd start
```

Open `http://127.0.0.1:5173/#live` in desktop Chrome or Edge. Select **AI screen
guide**, choose the service/model, enter the key and accept the displayed cloud
terms. Describe your goal, choose **Share a window**, then **Check screen**.
Review/crop/hide the image, tick the review box and choose **Send to OpenAI** or
**Send to Claude**. Perform the instruction yourself and check the updated screen.

Keep Guider visible beside the source window. Hiding its tab stops sharing.
Sharing expires after 15 minutes and the key connection after 30 minutes.
There are at most 40 admitted checks per connection and at least two seconds
between checks. Disconnect clears the key; restart/refresh does not restore the
connection. Frames and answers in this workflow are not saved by Guider.

Use the ordinary launcher for this workflow: the personal API checks the actual
loopback peer, which the existing Docker networking does not preserve.
Ports 5173 and 8000 must be available. `npm.cmd` avoids the PowerShell script
execution-policy failure encountered with `npm.ps1` during this review.

## Useful improvements after the first successful trial

These are optional improvements, not missing requirements for the basic loop.

- [ ] Add an explicit personal-guidance start link or remembered mode so returning
  users do not always land in the demo walkthrough.
- [ ] Show remaining connection time/check allowance and clearer reconnection
  prompts before the existing limits are reached.
- [ ] Add a backend-readiness indicator and an optional Windows launch shortcut.
- [ ] Define whether personal guidance needs opt-in export or history. Today it
  carries the preceding step and current question, not a durable task transcript.
- [ ] Make provider/model offerings discoverable from backend capabilities and
  validate the chosen live models, reducing duplicated frontend/backend lists.
- [ ] Add an integrated personal browser/API test harness. Browser personal-guide
  tests mock the local HTTP API; backend tests separately exercise the real API
  with mocked vendor transport. The new tests cover the two reported defects,
  but a joined test would catch future frontend/backend drift earlier.
- [ ] Improve Windows test setup: the root `npm test` command encountered an
  inaccessible reused pytest directory, and the default browser run failed in
  browser setup. A fresh pytest base directory and installed Chrome allowed
  checks to progress. Keep test-artifact failures distinct from app failures.

## Remaining work outside the selected scope

| Workstream | Remaining tasks | Needed for personal browser guidance? |
|---|---|---|
| Saved tasks/history | Configure matching Supabase web/backend settings; exercise real email sign-in, refresh, revocation and account lifecycle; configure a saved-task provider and encryption keys; test backup/restore. Browser demo history clears on refresh. | No |
| Saved-task OpenAI support | OpenAI currently declares only the personal `guide` role. Supporting it for saved analysis/planning/observation requires additional adapters or role implementations. | No |
| Native Windows client | Real PKCE callback/token exchange and storage; user-selected capture; native overlays; DPI/multi-monitor/protected-window handling; accessibility; installer, signing and updates. Current client is a shell with synthetic PKCE primitives. | No |
| Public deployment | Hosting/TLS/region; private object storage/KMS; OS-restricted decoding; durable task/account deletion outbox; orphan and backup erasure/restore; distributed admission and crash-safe provider accounting. | No |
| Release evaluation | Reviewed provider/model/retention scope; approved observation notice; measured guidance accuracy, false advances, latency and cost; supported application/OS/locale/display and accessibility matrix. | Only a small personal trial now; full certification later |

The production startup guard remains in place. Detailed public/native gates and
historical evidence are in [23](23-completion-checklist.md) and
[24](24-local-deployment-and-release.md). Older missing-feature lists in
[19](19-implementation-status.md) are historical, not the current personal backlog.

## Verification from this review

Fresh checks and their limitations are recorded here, rather than copying the
older release counts:

- Web unit tests: 175 passed before the fixes.
- TypeScript/web build: passed before and after the fixes.
- Browser baseline: 66 passed using installed Chrome. Capture and provider
  responses are simulated.
- Backend lint and SQLite migration/model parity: passed.
- Backend baseline with a fresh pytest directory: 516 passed, 12 PostgreSQL-only
  checks skipped. The root test invocation hit Windows permissions on its reused
  pytest directory, including an elevated retry.
- Post-change provider/API regression suite: 49 passed, including the new Claude
  connection regression. Backend lint also passed.
- Post-change browser checks: all 11 personal-guidance and demo scenarios passed,
  including the new Claude disclosure/review/send scenario.
- Initial focused regression attempts timed out in demo progression and backend
  cancellation; reruns passed without changing their assertions or timeouts.
  This review does not establish the cause of those transient failures.
- Launcher smoke check: web and API returned HTTP 200; the personal-connection
  route is present. No external provider request was made by this smoke check.
- PostgreSQL, native builds, containers, real Supabase and real provider calls
  were not re-certified in this personal-browser review.
