# Personal website: automatic screen guidance

Updated 2026-09-22. Selected scope: a website usable from multiple computers,
with your own OpenAI or Anthropic key. The implementation is ready for a hosted
personal trial; no public deployment or real provider trial has been completed.

## What is implemented

- Sign in by email code. Hosted sign-in survives refresh. The same account can
  reuse its encrypted provider keys on another computer.
- Remember, replace and forget a key. Plaintext provider keys are never returned
  by the API or stored in browser storage. The API decrypts them when contacting
  the selected provider. This is server-side encryption, not end-to-end encryption.
- Enter a goal and optionally paste instructions. Guider proposes up to 20 steps,
  assumptions and visible success criteria. Review and confirm before capture.
- Approve installation, downloads and settings changes separately when that step
  is reached. You perform every click and command yourself. Passwords, payments,
  elevated administration, destructive actions and publishing remain unsupported.
- Choose one window or browser tab, preview it and mask private areas. Explicitly
  start automatic sharing. Guider checks stable frames as the screen changes,
  gives a small next action, and can place an arrow and small "Next click" label
  over the shared-screen preview in Guider. You click in the original window.
- The optional [Chrome/Edge tab companion](../../user-mode/extension/README.md)
  places the ball, step messages and click markers directly inside the chosen
  website. Install it once per browser profile, explicitly connect Guider and the
  target tab, then share that exact browser tab. Capture Handle checks their
  identity. Scrolling/page changes clear stale arrows. Full page navigation
  removes the overlay and stops sharing; re-enable it on the new page to continue.
- Automatic progression requires the model to report visible completion with
  high confidence. This is a model judgment, not proof of successful installation.
- A small round button opens a menu with the current step, Pause/Resume, Stop,
  return to the shared preview and Exit. Short chatbot-style bubbles announce
  the next action, step completion, approvals and task completion. Dismiss a
  bubble to keep only the ball; Show current step opens it again. There is no
  screenshot inside the floating control. In desktop Chrome/Edge the companion
  opens automatically in a separate always-on-top Document Picture-in-Picture
  window when Start watching is clicked without a connected tab companion.
  Uncheck the floating-guide option to keep it on the Guider page instead.
  Closing that window stops sharing. Automatic sharing continues when you switch
  tabs or applications, even without the floating window. Return to Guider or use
  the browser's stop-sharing control to stop. Temporary source interruptions pause
  screen checks until frames return; they do not end sharing.

The website cannot place a native pointer directly over another application's
buttons, click for you, or silently change capture to a newly opened installer.
Stop and choose the new window when the task moves between applications. The
browser owns the floating window's frame and placement; it is not a borderless
iPhone-style system overlay. See [Chrome's Document PiP documentation](https://developer.chrome.com/docs/web-platform/document-picture-in-picture).

## Daily use after deployment

1. Open your Pages URL in desktop Chrome or Edge and sign in.
2. Select OpenAI or Claude, enter a key once, leave **Remember this key securely**
   checked, accept the provider notice and connect. Later, use **Use saved key**.
3. Enter a goal such as "Install VS Code using the user installer". Paste any
   steps you already have, then select **Analyze and make a plan**.
4. Read the plan and assumptions, tick the review box and **Confirm plan**.
5. For arrows on another website, follow the tab extension setup on the Automatic
   guide page. Choose **Choose window and permissions**, read the notice, select
   the connected browser tab, add masks and select **Start watching**. Without
   the extension, the floating guide opens automatically for use over other apps.
6. Follow the current instruction in the original application. Approve changes
   when requested. Guider checks again and advances when completion is visible.
7. Tap the guide ball and choose **Stop screen sharing** whenever needed. Pause stops capture too; resuming
   asks you to choose and review the window again. **Forget key** deletes the
   saved credential and closes that account's connections for that provider.

Screen sharing expires after 15 minutes; provider connections after 30 minutes.
Reconnect with the saved key instead of pasting it again. Reloading, signing out,
or redeploying stops the current session; plans are not saved as history.
The UI sends at most one frame every 10 seconds, checks an unchanged screen
periodically, and waits for stability. The API caps automatic frames at six per
minute and total AI requests at 120 per connection. Render's configuration also
sets a durable 200-request daily account cap, including key validation, failed
and canceled requests. These are request limits, not a currency spend cap.
Provider usage is billed to your account. Stopping cannot retract an image
already received by the provider.

## Publish once; use from any computer

Use **Cloudflare Pages + Render + Supabase**. Pages serves the React frontend;
the Python API runs on Render; Supabase supplies authentication and PostgreSQL.
Pages Functions use the Workers runtime and cannot directly run this existing
Uvicorn service. See [Pages Functions](https://developers.cloudflare.com/pages/functions/).

Only this personal API is deployed. `app.main:app` and its unfinished saved-task
product retain their production startup guard. Do not use the old Dockerfile or
full-product Compose file for this deployment.

### 1. Supabase: account and persistent storage

Create a Supabase project. Keep its project URL, publishable key and database
connection details available in the relevant hosting dashboards, not in Git.

- Enable email authentication and use asymmetric ES256 or RS256 JWT signing.
  This backend refuses legacy symmetric JWTs.
- Create/invite your account in Authentication > Users and record its user UUID.
  The website disables automatic signup; the API also requires an explicit UUID
  allowlist. Configure additional trusted accounts there when needed.
- Edit the **Magic Link** email template to display `{{ .Token }}`. The site
  accepts an email code, not a link callback. Follow [Supabase's OTP setup](https://supabase.com/docs/guides/auth/auth-email-passwordless).
- Configure mail delivery for your email address. Supabase's default sender has
  testing restrictions; configure your own SMTP when needed.
- Obtain the **session pooler** PostgreSQL connection from Connect (IPv4,
  normally port 5432). Use `postgresql+asyncpg://` as the scheme, URL-encode the
  database password and append `?ssl=require`. Use the project database owner's
  credentials only on Render. Avoid the transaction pooler for this configuration.
  See [Supabase connection choices](https://supabase.com/docs/guides/database/connecting-to-postgres).

### 2. Cloudflare Pages: obtain the frontend URL

Connect the Git repository to Pages, selecting the branch containing this change.

| Build setting | Value |
|---|---|
| Root directory | `user-mode/web` |
| Build command | `npm ci && npm run build` |
| Output directory | `dist` |
| Node version | `22.12` or a supported newer version |

You can create the first deployment to obtain `https://YOUR-SITE.pages.dev`, then
set the final variables below and rebuild after the API is ready. That initial
unconfigured build is only a demo, not the signed-in personal site.

### 3. Render: deploy the personal API

Create a Blueprint from the repository's root `render.yaml`. It uses
`user-mode/backend/Dockerfile.personal`. Fill its requested environment values:

| Backend variable | Value |
|---|---|
| `GUIDE_SUPABASE_URL` | `https://PROJECT.supabase.co` |
| `GUIDE_DATABASE_URL` | The asyncpg session-pooler URL described above |
| `GUIDE_ALLOWED_ORIGINS` | `["https://YOUR-SITE.pages.dev"]` |
| `GUIDE_PERSONAL_ALLOWED_USERS` | `["YOUR-SUPABASE-USER-UUID"]` |
| `GUIDE_CREDENTIAL_ROOT` | Generated by Render; keep it stable and back it up privately |
| `GUIDE_ENVIRONMENT` | `production` (already in the blueprint) |
| `GUIDE_PROVIDER_DAILY_CALLS` | `200` (adjust to your own request budget) |

The list values are JSON arrays, with no trailing slash on origins. Do not put
OpenAI or Anthropic keys in these variables; enter each user's key in the app.
Changing or losing the credential root makes existing saved keys unreadable.
Do not reuse the database password or Supabase signing secret as this root.

Startup initializes only `personal_keys` and `personal_budgets`, enables RLS and
removes public/anonymous/authenticated table grants. The backend database owner
accesses them; browsers cannot. This initialization is idempotent. Future table
changes will require an explicit migration; it does not upgrade the saved-task
schema. Keep exactly **one API instance and one Uvicorn worker**. Multi-instance
hosting needs shared session state and is outside this personal deployment.

Check `https://YOUR-API.onrender.com/health` returns the personal service status.

### 4. Set frontend variables and rebuild Pages

| Public frontend variable | Value |
|---|---|
| `VITE_PERSONAL_API_URL` | `https://YOUR-API.onrender.com/api/v1/local-guide` |
| `VITE_SUPABASE_URL` | The same Supabase project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Its publishable key |
| `VITE_API_URL` | Leave unset/blank for this mode |

Every `VITE_` value is public. Never use a Supabase service-role key, database
password, encryption root or provider key here. Rebuild after changing values.
The build emits Pages `_headers` with the configured API/Supabase CSP origins.
Add the final website URL to Supabase's Site URL configuration. If you add a
custom domain, also update the backend origin list and Supabase URL settings.

### Free tier limitations

This combination can be tried on free plans; AI calls are separate. Render's
free API sleeps after 15 idle minutes and can take roughly a minute to wake.
Its disk is ephemeral, which is why keys and daily counts use external
PostgreSQL. Supabase free projects can pause after inactivity. These limitations
make free hosting unsuitable for a promise of uninterrupted availability.
See [Render free services](https://render.com/docs/free) and
[Supabase project pausing](https://supabase.com/docs/guides/platform/free-project-pausing).

## Acceptance checks before relying on it

- Sign in on two computers and confirm a saved key works on both. Forget it on
  one and check it is unavailable on the other. Provider plaintext must not
  appear in browser storage, responses or host logs.
- Complete a real nonsensitive task with your chosen provider/model. Check the
  actual guidance, wrong-screen handling, latency, cost and false advances.
- Exercise the real window picker, masks, source closure, browser stop-sharing,
  floating-window closure, Pause, Stop and sign-out while a request is running.
- Verify real email delivery, JWT refresh, database connectivity, Render restart,
  the daily limit and restoring a backup together with its matching root secret.
- Review who can access the deployment's database/backups and host secrets.
  Restrict it to your accounts; this is not an unrestricted public-signup service.

Automated coverage uses synthetic provider replies, email authentication and
capture streams. The joined browser test exercises the actual hosted API,
encrypted SQLite storage, account-bound grants, refresh, consent, step approval,
automatic advancement, completion and forgetting a key. Windows tests exercise
real DPAPI locally. Real cloud services, PostgreSQL deployment and paid provider
calls still require the checks above.

## Local fallback

`npm.cmd start` at the repository root still runs the local app. Open
`http://127.0.0.1:5173/#live` and choose **Automatic guide**. It needs no Supabase.
On Windows, remembered keys use your Windows user's DPAPI-protected files under
the ignored backend `.local/personal-keys` directory; they do not sync to other
computers. Other local operating systems currently keep keys only in memory.

For the joined synthetic browser check, install backend/frontend dependencies
and run `npm run test:personal` from `user-mode/web`. On this Windows PC set
`$env:GUIDE_BROWSER_CHANNEL='chrome'` to use installed Chrome. Test servers exit
when the run finishes.

## Verification in this workspace

- Frontend: 183 unit tests and the default production build passed after the
  tab extension update. A hosted production build passed earlier.
  The hosted build's generated headers name only its configured remote services.
- Existing manual-guide browser regression: five scenarios passed.
- Personal browser/API integration after the tab extension update: five
  scenarios passed, including preview arrows, the 56-pixel round button, message
  dismissal, step/task-completion popups, menu Pause/Exit, a real Chrome Document
  PiP window, stopping on its closure, and stopping on sign-out. The companion
  contains no screenshot or video. The frontend production build also passed.
  The additional scenario covers the picker hiding Guider, preview attachment,
  temporary track mute without frame uploads, recovery and source ending.
  Four scenarios use synthetic capture streams and visibility/mute events.
  The extension scenario installs the companion in an isolated Chromium profile,
  captures a real fixture browser tab (auto-selected by a test-only browser flag),
  checks in-tab hints and clean screenshot pixels, rejects a mismatched capture
  handle, clears stale markers, stops on navigation, and checks Stop/Exit.
  It grants localhost permission to the test copy only, replacing the toolbar
  click that grants activeTab in normal use. Supabase and provider responses are
  synthetic. The interactive browser picker and real provider calls remain
  unverified. The packaged extension ZIP passes CRC validation.
- Backend lint and the full regression suite passed: 528 passed, 12 PostgreSQL-only
  checks skipped. This includes encrypted-key isolation/reuse, real Windows DPAPI,
  plan and capture consent, step approval, cancellation, uncertain/blocked results,
  frame-rate limits and durable daily admission.
- The Docker CLI is installed, but its engine is stopped. Image build/start and
  PostgreSQL deployment were not verified here. No real provider key was used.
