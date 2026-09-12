# 01 · Product requirements

Status: proposed MVP and explicitly labeled expansion. Repository facts: [18](18-repository-inspection-report.md). Contract authority: [README](README.md).

## Vision and problem

**Complete difficult computer tasks with a visual guide, one verified step at a time.** Users struggle to translate general answers into actions in an unfamiliar application. Error text lacks context, interfaces move, and long instructions overwhelm people. Repeated trial and error increases support time and interrupts practical work. Guide Mode couples an explanation to the user's visible context and checks the outcome before continuing.

This is not only a coding assistant. The same loop can support Windows troubleshooting, productivity, creative tools, browsing, study, professional work, communication and AI tools. A deliberately narrow first certification scope makes visual verification and privacy testable.

Target users: novice developers setting up a local project; students learning unfamiliar software; professionals troubleshooting their own desktop; independent users who need practical support. Initial pilot: adults using supported applications on their own desktop, in English. Shared institutional administration, child-specific experiences and organization-wide monitoring are future work pending D06.

## Principles and non-goals

User agency, explicit consent, one visible action, evidence before success, minimal data, honest uncertainty, accessible controls and stable service boundaries govern the product. Explain difficult actions and support manual alternatives. Never interpret screen content as authorization.

Non-goals: replacing a full IDE or course platform; writing entire projects automatically; remote desktop control; background productivity surveillance; unrestricted browser automation; executing commands or edits; solving CAPTCHA; diagnosing medical conditions; operating financial or regulated systems. A local terminal shown on screen is context, not an execution interface.

## Requirement register

| ID | Requirement and measurable acceptance |
|---|---|
| R01 | A simple homepage exposes Start a task, Upload a screenshot and Continue a previous task; no agent dashboard |
| R02 | Create a goal with category, application and optional context; clarify missing outcome without guessing |
| R03 | Upload, crop, redact, replace and delete screenshots before/during/after a failed step; paused sessions allow manual uploads |
| R04 | Accept bounded text and push-to-talk voice; show editable transcript before ordinary submission |
| R05 | Generate an editable, versioned plan with risk and success criteria; only an explicitly confirmed version can start |
| R06 | Observation defaults off; user can start and finish in screenshot-only mode after denying permission |
| R07 | Offer a draggable, accessible floating dot, compact panel and clear pointer without obstructing input |
| R08 | Show one instruction containing action, location, optional reason, confirmation method and cannot-find alternative |
| R09 | Record user completion separately from verification; only evidence-backed verification passes a step |
| R10 | Recheck, accept contrary evidence and revise after mismatch or incorrect guidance; never repeat indefinitely |
| R11 | Pause and emergency stop close capture locally, cancel work and invalidate pending pointers immediately |
| R12 | Stop terminates permission and overlay; summarize stopped versus achieved outcomes accurately |
| R13 | Resume persisted tasks after pause/restart only with review and fresh observation permission |
| R14 | Show private session history, summary, feedback and a next action; distinguish user-reported from verified outcomes |
| R15 | Supabase Auth authenticates web and Windows users; owner/device authorization isolates all task data |
| R16 | Enforce redaction, private storage, short media retention, deletion and minimal audit logging |
| R17 | Allowlist apps, block sensitive surfaces, and separate risk confirmation from plan approval |
| R18 | Treat screenshots, webpages, code and transcripts as untrusted data; validate all model output |
| R19 | Independent web/backend/Windows deployment; versioned authenticated APIs and bounded internal orchestration |
| R20 | Full session state machine supports timeout, permission loss, restart, race conditions and expiry |
| R21 | Multi-monitor, DPI, keyboard, contrast, screen reader and reduced-motion behavior meet test matrix |
| R22 | Network/provider/vision/voice failure leaves capture safe and provides recoverable manual guidance |
| R23 | Rate limits, operation budgets and content-free observability bound cost and abuse |
| R24 | MVP certifies Setup, Run, Debug, Understand, Test, Git and GitHub workflows in named apps |
| R25 | Retain a multi-domain taxonomy without implying all listed apps are currently supported |
| R26 | Future learning handoff is optional, purpose-limited and Agent Zero-authorized; basic Guide works alone |
| R27 | Signed Windows packaging, safe updates, explicit startup and crash recovery; no startup monitoring |
| R28 | Contract, retention, security, UX and Windows acceptance tests gate each implementation phase |
| R29 | No send/publish/submit or other high-risk instruction without specific confirmation where permitted; blocked categories remain blocked |
| R30 | Source inspection, ADRs and traceability prevent invented legacy contracts and architectural drift |

## Primary journeys

| Journey | User goal | Evidence and completion |
|---|---|---|
| Debug Python | “Why does this import fail?” with a cropped error | Explain observed error; point within screenshot; guide interpreter selection; verify a new run result |
| Set up VS Code | Configure an existing project | Confirm plan; choose screenshot-only or one app window; guide one setting; verify visible configuration |
| Run a web app | Find why localhost does not open | Ask terminal/browser context separately; identify port; user runs command; verify response without claiming deployment |
| Understand software | “What does this panel mean?” | Explain only visible controls; user confirms understanding as self-report, not objective task success |
| Recover when stuck | “That button isn't there” | Remove stale pointer; request new crop; revise current step and reconfirm plan if scope changes |
| Future productivity | Fix Word formatting or Excel formula | Post-MVP application pack with document-specific verifiers; same permission and risk policy |
| Future learning | Repeated Python debugging difficulties | Offer an optional learning path with an explicit preview of shared summary; no automatic enrollment |

## Platform and application scope

MVP: Windows 11 x64 primary; Windows 10 22H2 x64 compatibility target with security-servicing eligibility decided at D03. ARM64, macOS, Linux native overlays, mobile and remote/virtual desktops are future certification. The web application provides screenshot help without installing Windows software; live observation requires the native client and an interactive local desktop.

Windows 10 general support ended on October 14, 2025. Compatibility alone does not establish a supported security posture; production Windows 10 distribution is gated on a documented servicing policy. [Microsoft lifecycle notice](https://learn.microsoft.com/en-us/lifecycle/announcements/windows-10-end-of-support).

MVP applications: VS Code; PowerShell and Windows Terminal; Chrome and Edge; Git CLI and GitHub's ordinary repository pages; Python and JavaScript/TypeScript development; basic Docker Desktop status and ordinary container troubleshooting. React/Next.js symptoms may be explained as JavaScript project context, without a promise to fix every framework or deploy a service. GitHub credential entry, security settings and organization administration are excluded.

The first six categories share goal → context → instruction → visible evidence. They offer reproducible test fixtures and bounded changes. Broad Office, creative and enterprise coverage would multiply interface and verifier uncertainty before the core loop is reliable. [10](10-task-taxonomy.md) lists each domain and task without inflating MVP support.

## Safety scope

| Disposition | Tasks | Product behavior |
|---|---|---|
| Completely blocked in MVP | Banking, transactions, payments/purchases, password-manager interaction, password entry, medical systems, government portals, legal submissions, CAPTCHA, security-sensitive account changes, high-risk administrative changes | Stop guidance on that surface, remove pointer, close capture, explain limit; no confirmation override |
| Execution completely blocked | Automatic file deletion; automatic email/messages; automatic content publication; unrestricted mouse/keyboard control; shell execution; file modification | No execution tools or endpoints exist; user confirmation cannot enable them |
| Guidance requires specific confirmation | User-performed ordinary file deletion, Git push, message/email send, ordinary web-form submission or content publication within a supported workflow | Show exact target/consequence and a fresh action-specific confirmation before actionable final-step guidance; Office/content workflows remain post-MVP |
| Medium-risk guidance | Ordinary app installation from official source, project settings, PATH edits in user scope, user-performed file edits | Explain source/scope/rollback and confirm the concrete change; elevated changes are blocked |
| Unsupported until expansion | Arbitrary enterprise apps, complex 3D tools, broad creative/professional integrations | Explain supported alternatives using sanitized screenshots; do not claim live app support |
| Never a background feature | Continuous desktop monitoring or capture after pause/stop/close | Fail closed and require new local permission |

Preparing draft text or explaining a command is distinct from submitting it. Even within an approved task, external action confirmation is fresh, specific and separate from visual verification. See SEC-07 and SEC-08 in [09](09-security-and-privacy.md).

## Scope and release measures

MVP includes all R01–R24 and R27–R30 within the allowlist, with R25 taxonomy and R26 interface design only. Post-MVP: Office, creative, broader troubleshooting and professional app packs, additional languages, provider options and offline models. Future: Agent Zero coordination, Atlas teaching, Scout learning transition and institutional policies. No roadmap item implicitly enables automated control.

Proposed pilot: 30 consenting users, 100 bounded tasks across the six categories, a fixed versioned fixture set, no claims of statistical generalization. Collect aggregate outcomes with opt-in analytics. Targets: ≥75% independently verified supported-task completion; ≥90% first-instruction clarity rating 4/5 or higher; ≤2% false verification passes in labeled test evidence; zero unauthorized capture/actions and zero cross-owner access. Pauses and stops must pass 100% of safety tests. Latency targets: first explanation p95 ≤15 s; recheck p95 ≤10 s under declared network/hardware; local capture-disable p95 ≤100 ms and max 250 ms. All are targets, not measured results.

Count completed tasks with outcome `achieved` separately from `user_reported`, `stopped`, failures and unsupported requests. Time-to-resolution excludes user-chosen long pauses but reports active and elapsed time separately. Track step revisions, unclear evidence rate, screenshot-only completion, opt-in observation rate, safety blocks, per-task provider cost and deletion SLO. Do not treat more observation time as success.

## Assumptions, risks, dependencies and unresolved decisions

Assume users can perform ordinary actions and intentionally provide context. Vision may misread text, lack current app knowledge or miss secrets. Mitigate with crops, evidence freshness, local privacy checks and manual alternatives. Other risks: Windows capture variability, EOL systems, app UI changes, injection, false verification, cloud cost and provider retention. No automated sensitive-content detector is guaranteed complete.

Dependencies: 05/07/08/09 contracts before coding; native capture spike before live pilot; signed packaging and provider review before real data. D01–D07 in [README](README.md) remain open. Traceability: R01–R30 map to functional IDs, tests and phases in [17](17-traceability-matrix.md).
