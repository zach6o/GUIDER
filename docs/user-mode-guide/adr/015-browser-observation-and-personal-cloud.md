# ADR-015 · Browser observation and personal OpenAI connection

Date: 2026-09-07. Status: accepted for the local development application at the user's explicit request for screen observation and cloud guidance using an OpenAI API key. This supersedes the screenshot-only phase order for this narrowly scoped local workflow.

## Decision

Add a browser window/tab picker, a visible live preview, user-triggered frame checks, crop/hide review before each cloud submission, and one-step OpenAI vision guidance. The browser streams selected pixels locally; it does not send video or take periodic cloud snapshots. Full-monitor selection is rejected. Stopping, hiding the Guider tab, navigation, source loss, offline state, expiry and unmount close tracks and invalidate pending guidance. Reconnection needs a fresh picker gesture.

Use OpenAI Responses with image input, a strict response schema, no tools and `store=false`. The selected model is shown before consent. A user enters their own key in the app; it is sent only to the loopback backend, retained in memory for at most 30 minutes, and cleared on disconnect/server restart/expiry. The browser clears the key field after connection. The backend contacts only `https://api.openai.com/v1` with TLS and no redirects.

The new `/api/v1/local-guide` router is an explicitly local, ephemeral cloud connector, not an account API or Supabase replacement. It exposes no saved tasks, storage, account records or native grants. It requires a loopback client, exact localhost Host and trusted local browser Origin. A connection issues an unpredictable capability token held only in browser memory; all subsequent checks/cancel/disconnect calls require it. Supabase remains mandatory on `/api/v1/guide` and production remains gated. This allows the requested personal workflow to function without first deploying an account system.

## Consent and limits

Each captured still is reviewed and optionally cropped/hidden before **Send to OpenAI**. Live preview is local. Keys are never placed in source, localStorage, query strings or logs. Images/results are not persisted by the local connector. OpenAI account billing and data policies apply; `store=false` is not a promise of zero provider retention. Disconnect cannot retract a request already received by OpenAI.

One request at a time, at least 2 seconds apart, up to 40 checks/connection, 4 MiB provider images, 2,560px maximum edge and bounded text/output/time. Keep only the current answer in the UI, clear it on new frame or stop, and pass a bounded previous step as untrusted context when rechecking. No execution, clicking, typing, recording, automatic success claim, or automatic resumption.

## Explicit limitations

### Local demo addition (2026-09-08)

At the user's request, the screen-guide page defaults to an interactive practice app that requires no API key or backend. This replaces the initial Python result-button walkthrough. Four sample actions (Settings, Appearance, Dark theme, Save) demonstrate floating target hints, action detection, a checking phase and automatic next-step progression. A reducer verifies expected sample state before advancing. Wrong clicks cannot complete steps. Optional playback performs only these sample actions; Pause, Resume, replay, page hiding and unmount manage pending timers.

Optional window/tab mirroring places a live local preview behind the practice app and floating hints, simulating an overlay within the browser. Fullscreen previews this browser surface; it is not a native desktop overlay. Starting, changing or stopping mirroring pauses the guide. The demo does not take snapshots, infer anything from the selected window, contact the cloud connector, execute commands, interact with other applications, or claim a real task was verified. Changing mode closes tracks. The real-provider flow stays under **OpenAI guide**, with its per-frame review and consent unchanged.

Browser sharing cannot attest executable identity, enforce the native application allowlist, exclude password fields before acquisition, or implement desktop pointer overlays. This is a personal browser development feature, not certification of phase 4 or the native capture security specification. The source picker and an explicit sensitive-window warning are the available local boundary; users must choose a nonsensitive window and review each outgoing still. Strong native gates remain required for a distributed release.

## Sources and traceability

[W3C Screen Capture](https://www.w3.org/TR/screen-capture/), [OpenAI image input](https://developers.openai.com/api/docs/guides/images-vision), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [provider data controls](https://developers.openai.com/api/docs/guides/your-data).

R06/R08/R11/R16/R18/R22; SEC-03/04/05/09/10; new tests for stream disposal, picker races, stale response rejection, consent, local origin enforcement, cancellation and secret-safe provider failures. Documents 03/04/06/07/09/15/19 must reference this development exception without claiming native phase completion.
