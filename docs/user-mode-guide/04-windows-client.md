# 04 · Windows desktop client

Local development exception: [ADR-015](adr/015-browser-observation-and-personal-cloud.md) supplies browser window/tab sharing independently of the WPF scaffold. It does not implement native allowlisting, executable identity checks, desktop pointers or overlay capture. Native requirements below remain open; see [19](19-implementation-status.md).

Proposed deferral: [ADR-016](adr/016-web-first-tiered-observation.md) removes this client from the MVP path in favour of a web guidance surface using the Document Picture-in-Picture API, and archives the scaffold without deleting it. No Electron, Tauri or other native dependency replaces it. The native requirements in this document remain the target for a separately authorized native release, and the allowlist and executable-identity gates of [ADR-011](adr/011-application-allowlisting.md) stay required before any distributed release. See [20](20-guide-engine-migration-plan.md).

Status: proposed MVP. No Windows code was found. Proposed implementation: C#/.NET WPF desktop shell with Win32 interoperability and Windows.Graphics.Capture, selected in ADR-014. Pin a supported SDK/runtime in phase 0; do not infer one from this empty repository.

## UI surfaces

Separate native windows provide (1) interactive floating dot, (2) compact control panel/instruction card and (3) non-interactive pointer layer. The pointer layer is click-through and never captures keyboard input. The dot/panel receive input only in their visible bounds. No full-screen transparent window may intercept the desktop. Never inject mouse or keyboard events.

Dot default: 40 device-independent pixels, snap 12 DIP inside nearest monitor work-area edge; minimum 44 DIP accessible hit area. Drag to reposition, clamp to work area and avoid taskbar, instruction target and system notifications. Save only normalized edge preference per monitor, not screen contents. Keyboard menu supports Move → arrow keys (8 DIP, Shift 1 DIP), Enter save, Escape cancel, Reset position. Unplugging a monitor relocates the dot onto the primary work area.

| UI state | Appearance and accessible label |
|---|---|
| Active, observation off | Static outlined Guide icon; “Guide active; screen observation off” |
| Active, permitted observation | Distinct eye icon plus persistent “Observation on: [app]” text in card/panel; may acquire stills only on user recheck |
| Processing | Spinner with “Checking…” and Cancel/Pause always available; reduced-motion uses static progress text |
| Paused | Pause glyph and “Paused — screen observation off” |
| Warning/blocked | Warning glyph, brief recovery action, no pointer |
| Stopped | Brief accessible notification; **dot, card and pointer disappear**; stopped status is visible in ordinary launcher/history only |

At 15 seconds idle, only dot decoration may become subtle (minimum 70% opacity); controls restore on hover/focus/shortcut. Instruction text, warnings, privacy indicator and close/stop controls stay fully opaque with required contrast. No text fade. A session in `paused` keeps its dot/card; a stopped or terminal session does not.

Panel controls: text input/Send, push-to-talk mic/Cancel, Pause/Resume observation, Repeat instruction, Full explanation, Upload screenshot, Ask follow-up, Incorrect guidance, Stop session, Privacy controls. “Pause observation” pauses the session; questions and manual screenshots remain usable. “Resume” lets the user select screenshot-only or grant fresh window access. Close panel hides only panel; an explicitly labeled “Stop and close Guide” ends session and all overlays.

## Focus, keyboard and accessibility

New instructions do not steal focus from the user's application. Announce concise updates through UI Automation live regions; read full instruction only on request. Clicking dot or shortcut may focus panel intentionally; closing returns focus to the previous valid window. Escape closes panel without changing session; Stop remains separate. Tab order: instruction controls → input → mic → screenshot → pause → privacy → stop → close panel. Give icon controls names, state and tooltips.

| Shortcut default | Action |
|---|---|
| Ctrl+Alt+G | Open/focus Guide panel |
| Ctrl+Alt+P | Pause; when already paused opens Resume review (does not silently grant access) |
| Ctrl+Alt+S | Emergency Stop |
| Ctrl+Alt+R | Repeat readable instruction |
| Space on focused mic | Start/stop push-to-talk; never global microphone activation |

Register shortcuts only during active/paused sessions; detect collisions and offer remapping plus visible fallback buttons. Never swallow unrelated keys. Narrator, keyboard-only, high contrast, light/dark, 200% text, reduced motion and 100/125/150/200/250% DPI are release tests. Controls must remain usable on smaller work areas with scrolling, not fixed clipping.

## Capture and privacy engineering

Use OS window picker with an explicit local explanation of app, purpose, destination/provider, 15-minute maximum grant, still-capture triggers and Stop. Reject full-monitor selection in MVP. Match selected window against executable identity/publisher/path policy and sensitive-surface rules; a window title alone is insufficient. Read-only UI Automation may check password flags and current app identity locally; do not enumerate or upload the entire accessibility tree.

Check `GraphicsCaptureSession.IsSupported()` before offering live guidance. Windows capture availability can vary by hardware/system policy; show screenshot-only fallback. The Windows capture APIs support acquiring app-window/display frames and system selection UI. [Microsoft screen capture documentation](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture).

Keep the OS capture indicator where available and always render Guide's own active-observation indicator. Exclude owned overlay windows from capture where supported, but do not use exclusion as a security boundary. Verify the resulting image contains only the approved source. Protected content, secure desktop/UAC, lock screen, minimized/unavailable window and ambiguous sensitive content block capture; never bypass protections or run elevated to capture them.

Local emergency stop closes capture gate synchronously (target ≤100 ms p95, ≤250 ms max), disposes frame pool/session, drops encoded/upload queues, cancels microphone, hides all overlays and increments epoch **before** network calls. Backend cleanup is best effort with a 15-second lease deadline. Client close, sign-out, OS lock/suspend and network loss use the same fail-closed gate; lock/suspend/network loss pause, deliberate close/sign-out stop. A crash must leave no independent capture service alive.

Capture is in-process, demand-driven, no service or scheduled task. Heartbeat every 5 seconds while an observation grant is active; server lease expires after 15 seconds without a successful heartbeat. Backend checks JWT, device, epoch and lease on every frame. A permission grant lasts at most 15 minutes, cannot exceed session/token expiry, and requires a new local consent to renew after expiry. Heartbeats cannot renew permission or extend user inactivity.

## Geometry and rendering

Declare Per-Monitor V2 DPI awareness and handle DPI/work-area/display-change notifications. Windows provides per-monitor DPI behavior for adapting UI layout. [Microsoft High DPI reference](https://learn.microsoft.com/en-us/windows/win32/api/_hidpi/).

Use physical capture pixels and normalized provider-image boxes per [03](03-screenshot-and-vision.md). Render in each monitor's local DIP space. Test monitors on left/top with negative origins, portrait rotation, mixed DPI, primary changes, window straddling and docking. A straddled or geometry-changed target must be recaptured; if mapping cannot be proven, use the image viewer only. Marker defaults to outlined circle/arrow outside text/target with short label; no animated cursor-following. Never move the actual system cursor.

## Startup, shutdown, recovery and delivery

Client is manually launched, single user-scoped instance; no autostart or tray capture by default. Initial screen signs in through system browser, lists task recovery and links to web. Ordinary task URI activation may contain a task ID only; the separate exact auth callback may contain a short-lived PKCE code and state per SEC-02. Neither URI contains access/refresh tokens. Validate URI format and fetch task with auth; activation cannot start capture. Register device after authentication. Secure credentials per SEC-02.

Network outage: immediately pause, hide pointer, show last safe instruction labeled “Offline — not rechecked.” Retain only encrypted session ID/checkpoint locally; no raw media or voice upload backlog. On reconnect, fetch state, refresh auth, resolve stale version, and ask user to resume. Offline supports reading cached instruction/drafting text only, no model answer or verification. Backend restart invalidates leases; client pauses on heartbeat failure.

Client crash/relaunch: observation off, “Your last session was interrupted. Review before continuing.” New controller claim invalidates old epoch. Terminal sessions create successors when continued. Normal Stop never leaves tray-only capture or a hidden overlay. Keep uninstallation independent of network; user can delete server data through web.

Packaging: signed MSIX per user; bundled supported runtime; no admin requirement for the Guide. Separate backend URL configuration for dev/staging/prod, no embedded service secrets. Verify signed update identity/version and TLS origin, download with consent, apply only after session stop; retain last good installer for rollback, never downgrade silently. Signing/feed D04 is a distribution gate. Do not add automatic elevation to solve installer/capture issues.

## Assumptions, dependencies and decisions

D03 governs Windows 10 eligibility and ARM64; D04 release signing; D07 app/hardware/accessibility matrix. Phase 3 native spike must prove WPF/picker/overlay interoperability, latency and disposal before phase 4 media flow. SEC-02/03/05/06/12/15 apply. Example: moving VS Code to another monitor removes the marker, says “The window moved; choose Check again,” and leaves the instruction readable. Traceability: R07/R11/R12/R21/R27 → F07/F11/F12/F21/F27 → T07/T11/T12/T21/T27 in [17](17-traceability-matrix.md).
