# 11 · UX specification

Status: proposed MVP. UX IDs below are used in [17](17-traceability-matrix.md). The interface should feel like a practical helper, with one readable instruction and immediate user control.

## Screen inventory

| UX ID | Screen / primary content | Actions and behavior |
|---|---|---|
| UX01 | Homepage `/`: “What would you like to do?” | Start a task (primary), Upload a screenshot, Continue a previous task; last task card only if available; no metrics or agent graph |
| UX02 | Task creation `/tasks/new` | Six category tiles, goal textarea, optional supported app selector; “Not sure” app maps unknown; inline goal validation; explain expected result with one clarifying question |
| UX03 | Screenshot preview/editor | Visible crop, opaque Hide tool with keyboard rectangle adjustment, Undo, Replace, Delete, Upload/Cancel; byte/format errors inline; “Only this image will be shared”; exact post-redaction preview |
| UX04 | Plan review `/tasks/:taskId` | Short proposed steps with edit/reorder/remove, app/risk/success criteria and assumptions; one Confirm plan button; revised plan invalidates approval visibly |
| UX05 | Start/permission screen | Screenshot-only is default; live requires installed/signed-in native client; preview selected window and provider/retention; Allow this window / Use screenshots instead / Cancel; no bundled microphone grant |
| UX06 | Active overlay/session view | Single instruction card, short where/why, Done, Check again, I can't find it; dot opens compact panel; screenshot-only highlights stay in viewer |
| UX07 | Pause/offline | “Paused — screen observation off”; keep readable instruction marked not rechecked; Upload screenshot, Ask, Resume, Stop; no hidden active spinner/capture |
| UX08 | Error/blocked | Plain specific message and one recovery action; show manual alternative; no looping identical instruction or fabricated pointer |
| UX09 | Completion | Verified versus unverified steps, achieved/user-reported/stopped outcome, correction notes, next action; rate help/report incorrect; no automatic enrollment or publication |
| UX10 | Privacy `/privacy` and compact panel | Current app scope, observation/mic indicators, provider and retention disclosure, revoke, devices, screenshot/session/task/account deletion; show purge due date and pending/complete receipt |
| UX11 | History `/history` | Newest first, task/app/date/outcome; Continue explains paused resume versus new session; no expired image thumbnail; Delete session / Delete task clear scope |
| UX12 | Text/voice composer | Small text box and push-to-talk; mic status, timer, Cancel; editable transcript before Send; voice never approves sensitive actions |
| UX13 | Action confirmation | Concrete action/target/consequence/rollback; “Confirm guidance for [action]” / Cancel; expiry and target changes require new confirmation; no execution implication |
| UX14 | Launcher/recovery/update | Sign-in, last interrupted task review, trusted update notice while idle; observation off on startup; stop closes all overlay surfaces |

## Example interaction and instruction anatomy

User: “My Python file won't run.” Guide: “Please upload the terminal error, hiding any keys or personal details.” After review and analysis: “The screenshot shows that the selected interpreter cannot find the package.”

Current instruction card:

```text
Step 2 of 4 · Check the interpreter
What: Open the Python interpreter selector.
Where: In VS Code, use the Python version shown in the status bar.
Why: The package may be installed in a different environment.
When ready: Choose Done, then share the interpreter list to check it.
Can't find it? Open the Command Palette and search “Python: Select Interpreter”.
[Done] [I can't find it] [Why?]
Observation off · [Upload screenshot] [Pause] [Stop]
```

Only use this exact UI location if visible evidence/app context supports it; otherwise ask for context and show the command-palette alternative as a suggestion. Highlighting never replaces the textual location. `Done` is a completion claim, and the UI says “Let's check the result” instead of “Success.”

Plan review may show all steps to obtain meaningful approval; active mode shows one actionable step. Explanations can expand inline or in panel without replacing the current step. Avoid code dumps: show only the minimal command/snippet needed, label where user should type it, and explain any modifying effect before confirmation. Copy is explicit and never auto-pastes/runs. Repeating instruction neither advances state nor triggers capture.

## Permission and privacy interaction

Live choice: “Guide can take still screenshots of the window you choose when you ask it to check a step. Images go to [approved provider] and are deleted from Guide storage within 24 hours. You can pause or stop at any time.” The actual provider must replace placeholder before production. Show 15-minute grant maximum and active app scope. No “Always allow,” background mode or full desktop option.

Denied permission is a supported path, not a fatal error. “You can continue by uploading screenshots.” Pausing revokes the current grant; Resume first offers screenshot-only or a fresh window choice. Manual upload while paused is explicitly “Share this image while paused”; does not resume observation. Observation and microphone indicators use distinct icons and text, never color alone.

Sensitive surface: “Guide can't observe this screen. Return to a supported window or upload a redacted screenshot.” Do not display detected secret values in warnings. Delete image explains that associated visual evidence and derived context become unavailable. Delete session explains task-level context may remain; Delete task removes it all. Account deletion requires recent authentication and a concrete final confirmation; show offline/provider/backup erasure limits accurately.

## Accessibility, loading and focus

Keyboard-only flow must cover upload (file picker alternative to drop), crop/hide coordinates, plan edit/reorder, consent, all overlay controls and deletion. For image redaction provide numeric/arrow-based region selection with preview and descriptive region labels; do not force precision mouse drawing. Text contrast ≥4.5:1 ordinary text and ≥3:1 large text/nontext controls; focus outline ≥3:1. Minimum web targets 44×44 CSS px where feasible; native targets in DIP. Support 200% zoom/text scale, screen-reader names/status, high contrast and reduced motion.

Announce processing start/result once through polite live region; urgent stop/privacy failure through concise assertive announcement. No focus theft from native work application for a new instruction. User opens panel deliberately; focus returns on close. Global shortcuts and collisions per 04. Never fade instruction text; dot decoration alone may become subtle after 15 seconds. No time-limited toast as the only error or privacy notice.

Loading copy uses bounded stages: “Uploading image,” “Reading the selected area,” “Preparing your next step,” “Checking the result.” Show elapsed state after 5 seconds and Cancel/Pause; after operation deadline show recovery per 14. Do not fake percentage progress. Cancel stops the operation, invalidates pointer, and preserves safe task state; it does not imply remote provider bytes were never received.

## Assumptions, dependencies, decisions and traceability

English first; voice accessibility is supplemental, not required to operate. D07 governs usability/accessibility certification and translations. Depends on 02–05 and atomic instruction API in 07; SEC-03/04/05/08/15 gate UI. Example flows are implementation fixtures, not evidence of existing screens. R01/R03–R14/R21/R27/R29 → corresponding F/T entries in [17](17-traceability-matrix.md).
