# ADR-022: Account-bound personal website

Status: implemented for personal trial, 2026-09-22.

The user selected a public website usable from multiple computers and requested
remembered OpenAI/Anthropic keys, goal or pasted-step planning, reviewed
permissions, automatic screen guidance and a floating stop control.

The narrow personal runtime is `app.personal_app:create_personal_app`. It exposes
only the personal connection and planning/observation routes, uses Supabase JWTs
plus a UUID allowlist, and stores encrypted keys and durable daily admission in
separate PostgreSQL tables. Capture media and plans are transient. Credentials
are bound to owner and provider in the encryption envelope. One process and one
instance own short-lived connection capabilities and cancelable observation.

The earlier loopback connector stays loopback in `app.main`; its production guard
is unchanged. That full saved-task product is not made releasable by this ADR.
The hosted personal frontend is selected explicitly by `VITE_PERSONAL_API_URL`.
It persists the Supabase session, never the provider key, in browser storage.

The automatic route uses a separate plan/permission policy: ordinary installation
and configuration may be guided after current-step approval. Guider executes no
actions. Sensitive, destructive and elevated operations remain unsupported.
Automatic frames require confirmed plan and separately accepted capture scope.
Browser Document PiP provides visible external controls; closing it stops capture.
Automatic sharing continues when the page is hidden, including when the browser
picker switches to the selected tab. Temporary track mute pauses frame submission
until the source recovers. Stop, source ending, page closure, offline and the
15-minute capture expiry still end sharing. Rate/session limits bound observation.

An optional Manifest V3 Chrome/Edge companion uses only activeTab and scripting
permissions. Users explicitly pair the Guider page and target tab. Capture Handle
binds the overlay to the browser tab actually being shared; a mismatch blocks
watching. Extension messages carry only current-step display data and controls,
never keys or screenshots. The overlay hides during fresh-frame capture, clears
stale targets on page changes, and removes itself on disconnect/navigation.
Navigation stops capture and requires re-enabling on the new document. The
website packages an unpacked-extension ZIP; no extension-store release is claimed.

This is a limited personal deployment, not anonymous public signup or a certified
native observer. Real provider accuracy, browser capture, PostgreSQL, email and
hosting acceptance remain required. Decoder isolation, multi-instance state,
durable task history and generalized account lifecycle remain outside this
runtime. Server-side envelope encryption means the host can decrypt saved keys;
the website must not claim end-to-end encryption.

Deployment and acceptance steps: [personal website guide](../26-personal-automatic-guide.md).
