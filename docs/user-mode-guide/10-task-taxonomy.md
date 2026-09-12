# 10 · Task taxonomy and capability matrix

Status: proposed capability catalogue. **A listed task is not necessarily supported in MVP.** R24/R25 require limited initial app certification and broad future domain design. Policy in [09](09-security-and-privacy.md) overrides every row.

## How to read the task matrix

Every task row supplies task name, category, application, user goal, context/verifier/failure profile, risk and release. Profiles below are normalized columns shared by each row: they explicitly define required context, screenshot sufficiency, live observation need, file access, voice utility, required verifier and possible failures. There are no unspecified inherited values. `M` = proposed MVP after app-pack acceptance; `P` = post-MVP expansion, not a current support promise; `F` = future research only. `L` low risk; `M` medium, concrete change confirmation; `H` high, action confirmation if permitted; `B` blocked by SEC-07 regardless of release. A task with mixed actions is classified at its highest actionable risk; explaining its safe portions may remain low-risk.

MVP categories: Setup, Run, Debug, Understand, Test, Git and GitHub (wire keys in 08). Future category labels below are taxonomy metadata only; do not send them to v1 create-task API until enum expansion is reviewed. Every row's expansion status is explicit in Release: M = expand within named app after fixture tests; P = requires a new app/verifier pack; F = separate discovery/ADR.

| Profile | Required context | Screenshot sufficient? | Live observation needed? | File access needed? | Voice useful? | Required verifier | Failure codes |
|---|---|---|---|---|---|---|---|
| ERR | Visible error, app/version, preceding user action, expected result | Yes for diagnosis; new image/output for outcome | No; optional approved window | No; user may paste redacted excerpt | Yes | Error resolved in new run/output, not just editor change | a,b,c,d |
| SET | OS/app version, current setting, intended change/source | Yes with before/after | No; optional approved window | No; user handles files | Yes | Visible setting plus benign functional check | b,c,e,f |
| RUN | App/project command, terminal output, expected endpoint | Yes with new run result | No; optional terminal/browser separately | No | Yes | Visible success/output or response tied to current run | a,c,d,g |
| CODE | Minimal redacted code/config excerpt, error and goal | Yes for explanation; outcome needs run/test evidence | No; optional IDE | No; snippet upload is text, not repo access | Yes | User runs scoped test; output matches criterion | a,c,d,h |
| GIT | Repository identity, branch, status/diff screenshot, intent | Yes, separate evidence after change | No; optional terminal/GitHub | No; user inspects repo | Yes | Relevant status/log/remote result; secrets review before push | c,e,h,i |
| READ | Visible page/diagram/panel and specific question | Yes | No; optional only for allowlisted MVP app | No | Yes | Referenced visible labels/source; comprehension self-report labeled | a,b,j |
| DOC | Redacted document region, desired layout/output | Yes with before/after/export preview | No; live only after app pack | No; user opens/exports | Yes | Visible layout/output inspection, print preview when relevant | a,b,e,k |
| SHEET | Formula/cells, headers, sample values, expected result | Yes for bounded cells; large workbook needs future file consent | No; live only after app pack | No in MVP/P screenshot workflow | Yes | Known sample calculation and visible cell result | a,h,k |
| DESIGN | Relevant canvas/layers/export panel and target design | Yes for bounded task | No; live only after app pack | No | Yes | Visible result and export properties | a,b,k,l |
| NAV | Current page/origin, ordinary destination and goal | Yes if non-sensitive | No; optional approved browser window | No | Yes | Visible destination/state plus explicit user result | b,e,g,i |
| DEVICE | OS/app version, settings/status, physical symptom | Sometimes; physical state requires self-report | No | No | Yes | OS test output plus explicitly labeled physical self-report | b,e,f,m |
| SEND | Draft preview, exact destination/account/visibility and intent | Yes with safe preview and later receipt | No; live only supported surface, no credentials | No | Yes for drafting; never confirmation | Fresh target-bound confirmation then user action and visible receipt, limited to observable result | e,i,n |
| SECRET | Sanitized settings, placeholder key name and intended service | Only redacted image; never secret entry | No; observation off during credential work | No | Yes for explanation; no spoken secrets | Non-secret connection/usage status, user private entry | e,g,o |

Failure dictionary: a unreadable/cropped evidence; b UI/version/language changed; c stale or wrong project/window; d output does not prove runtime success; e permission/safety restriction; f elevated/system change or servicing mismatch; g network/port/service unavailable; h missing context/dependency or nondeterministic result; i wrong destination/account/branch; j source uncertainty/unsupported inference; k hidden content/export/print differs; l layer/format mismatch; m physical result not visually observable; n irreversible external action/no receipt; o secret exposure/provider usage ambiguity. Recovery is specified in 14; screenshot sufficiency never authorizes guessing.

## Developer and technical work

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Coding errors | Debug | VS Code | Identify and resolve a visible coding error | CODE | M | M |
| Python errors | Debug | VS Code/PowerShell | Resolve a scoped Python traceback | ERR | M | M |
| JavaScript and TypeScript errors | Debug | VS Code/browser | Resolve compile/runtime error | CODE | M | M |
| React and Next.js issues | Debug | VS Code/Chrome/Edge | Explain and test a bounded framework symptom | CODE | M | M |
| Git and GitHub | Git and GitHub | Git CLI/GitHub | Review changes, commit and optionally push after confirmation | GIT | H | M |
| APIs | Debug | Browser/terminal | Understand request/response errors without secrets | RUN | M | M |
| Databases | Debug | VS Code/terminal | Explain a local query/connection symptom; no destructive query | CODE | M | M |
| Docker | Run | Docker Desktop/terminal | Inspect ordinary local container status/logs | RUN | M | M |
| Environment variables | Setup | VS Code/PowerShell | Configure a non-secret project variable | SET | M | M |
| Local servers | Run | Terminal/browser | Start and verify local server manually | RUN | M | M |
| Deployment preparation | Test | VS Code/terminal | Check build/config readiness without deploying | CODE | M | M |
| Browser DevTools | Debug | Chrome/Edge | Inspect a visible console/network symptom | ERR | L | M |
| Terminal and PowerShell | Understand | Windows Terminal/PowerShell | Explain commands/output and guide benign execution by user | RUN | M | M |
| Project configuration | Setup | VS Code | Correct bounded project setting with rollback | CODE | M | M |
| Reading technical documentation | Understand | Chrome/Edge | Relate visible documentation to current task | READ | L | M |
| Test failures | Test | VS Code/terminal | Interpret a failure and verify a focused fix | CODE | M | M |
| Dependency conflicts | Debug | Terminal/VS Code | Compare installed/required versions and recheck | ERR | M | M |
| Authentication configuration | Setup | VS Code/browser | Explain placeholders and non-secret redirect config; no account security changes | SECRET | M | M |
| Network and port problems | Debug | Terminal/browser | Identify local bind/port symptom without firewall changes | RUN | M | M |

## Windows and computer troubleshooting

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Installing and uninstalling applications | Setup | Browser/Windows Settings | Review official installer/uninstall scope; user performs ordinary change | SET | M | P |
| Windows settings | Setup | Settings | Find and change an ordinary preference | SET | M | P |
| PATH configuration | Setup | PowerShell/VS Code | Inspect and adjust user-scope developer PATH | SET | M | M |
| Network issues | Troubleshoot | Windows Settings | Diagnose ordinary connectivity; no security weakening | DEVICE | M | P |
| Microphone and camera problems | Troubleshoot | Settings/app tests | Check selected device and ordinary permissions | DEVICE | M | P |
| Printer and external-device setup | Setup | Settings/vendor app | Set up supported device using trusted instructions | DEVICE | M | P |
| File and folder management | Organize | File Explorer | Organize named user files, confirm any deletion | DOC | H | P |
| Application permission issues | Troubleshoot | Settings | Understand denied ordinary app access without bypassing policy | SET | M | P |
| Error dialogs | Debug | Supported MVP apps | Explain a visible ordinary application error | ERR | L | M |
| Display settings | Setup | Settings | Adjust resolution/scaling with recoverable steps | SET | M | P |
| Storage issues | Troubleshoot | Settings/File Explorer | Interpret storage use; no automatic cleanup | READ | L | P |
| Slow applications | Troubleshoot | Task Manager/app | Identify visible resource symptoms | DEVICE | L | P |
| Startup applications | Setup | Task Manager/Settings | Review ordinary startup entries | SET | M | P |
| Task Manager | Understand | Task Manager | Read processes/resource columns; no arbitrary termination | READ | L | P |
| Basic driver issues | Troubleshoot | Device Manager/vendor docs | Explain status and official recovery; privileged changes blocked | DEVICE | L | P |
| Terminal configuration | Setup | Windows Terminal/PowerShell | Configure ordinary profile/display settings | SET | M | M |
| Windows developer settings | Setup | Settings | Explain developer options; security/elevation changes blocked | READ | L | P |

MVP Setup can guide installing a named developer tool from its official page only within supported browser/terminal context. General Windows installer/Settings UI certification remains P. Elevated installer surfaces are never observed; do not conflate technical tool setup with unrestricted app administration.

## Office and productivity

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Microsoft Word | Document | Word | Complete a bounded document edit | DOC | M | P |
| Microsoft Excel | Spreadsheet | Excel | Explain and correct a bounded sheet task | SHEET | M | P |
| Microsoft PowerPoint | Presentation | PowerPoint | Edit a slide with verified layout | DOC | M | P |
| Google Docs | Document | Docs in browser | Format a document without sharing/submitting | DOC | M | P |
| Google Sheets | Spreadsheet | Sheets in browser | Fix a formula or chart with sample values | SHEET | M | P |
| PDFs | Understand | Browser/PDF viewer | Explain visible PDF text or controls | READ | L | P |
| Document formatting | Document | Word/Docs | Adjust headings, spacing or page layout | DOC | M | P |
| Spreadsheet formulas | Spreadsheet | Excel/Sheets | Build and validate a scoped formula | SHEET | M | P |
| Charts | Spreadsheet | Excel/Sheets | Choose and verify a chart from selected cells | SHEET | M | P |
| Presentations | Presentation | PowerPoint/Slides | Prepare readable slides | DOC | M | P |
| File conversion | Document | Office/PDF tools | Convert user-selected document with output check | DOC | M | P |
| Printing | Document | Office/print dialog | Review pages and user-confirm print destination | DOC | M | P |
| Exporting | Document | Office/PDF tools | Produce a selected format in user-selected location | DOC | M | P |
| Templates | Document | Word/PowerPoint | Apply and customize a template | DOC | M | P |
| Recovering unsaved work | Troubleshoot | Office recovery UI | Find a recovery copy without overwriting blindly | DOC | M | P |
| Organizing files | Organize | File Explorer | Name/group documents with explicit deletion confirmation | DOC | H | P |

## Design and creative tools

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Canva | Design | Canva | Edit a bounded design and preview output | DESIGN | M | P |
| Figma | Design | Figma | Adjust a visible frame/component | DESIGN | M | P |
| Photoshop | Design | Photoshop | Perform a basic visible image edit | DESIGN | M | P |
| Premiere Pro | Edit media | Premiere Pro | Explain basic timeline/export workflow | DESIGN | M | P |
| CapCut | Edit media | CapCut | Make a bounded clip edit | DESIGN | M | P |
| Basic image editing | Design | Supported editor pack | Crop/resize/color-adjust user image | DESIGN | M | P |
| Background removal | Design | Canva/Photoshop | Select and remove background with preview | DESIGN | M | P |
| Social-media designs | Design | Canva/Figma | Prepare a design draft; no publication | DESIGN | M | P |
| Posters | Design | Canva/Photoshop | Align text/images for poster output | DESIGN | M | P |
| Thumbnails | Design | Canva/Photoshop | Make a legible thumbnail preview | DESIGN | M | P |
| Export formats | Design | Creative app pack | Choose format/size and inspect output | DESIGN | M | P |
| Layers | Understand | Photoshop/Figma | Explain visible layer structure | DESIGN | L | P |
| Layout problems | Debug | Canva/Figma | Resolve overlap/alignment in visible canvas | DESIGN | M | P |
| Presentation design | Presentation | Canva/PowerPoint | Improve slide hierarchy and export preview | DESIGN | M | P |

Complex 3D tools are F and unsupported: screenshots may receive general explanation only in a later separately scoped product, with no MVP live allowlist entry.

## Browser and internet tasks

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Browser settings | Setup | Chrome/Edge | Change ordinary display/download setting; no security weakening | SET | M | M |
| Website navigation | Understand | Chrome/Edge | Find a named ordinary control/page | NAV | L | M |
| Downloading files | Setup | Chrome/Edge | Select trusted developer download and inspect source | NAV | M | M |
| Browser errors | Debug | Chrome/Edge | Understand a local app/browser error without bypassing TLS warnings | ERR | L | M |
| Cache management | Debug | Chrome/Edge DevTools | Clear local development cache with scope confirmation | SET | M | M |
| Permission settings | Setup | Chrome/Edge | Review ordinary mic/camera permission; sensitive account changes excluded | SET | M | P |
| Online tools | Understand | Chrome/Edge | Understand a visible ordinary tool | READ | L | P |
| Ordinary web forms | Browser workflow | Chrome/Edge | Prepare ordinary nonregulated form, confirm final submit | SEND | H | P |
| Documentation websites | Understand | Chrome/Edge | Find and interpret relevant docs | READ | L | M |
| Browser-based workflows | Browser workflow | Chrome/Edge | Complete a bounded ordinary workflow | NAV | M | P |
| Comparing information | Research | Chrome/Edge | Compare visible sources with attribution and uncertainty | READ | L | P |
| Understanding web pages | Understand | Chrome/Edge | Explain visible ordinary page content | READ | L | M |

## Study and research

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Explaining textbook screenshots | Study | Image/PDF viewer | Explain a selected passage without inventing hidden context | READ | L | P |
| Explaining diagrams | Study | Image/PDF viewer | Interpret visible labels/relationships | READ | L | P |
| Understanding research papers | Research | Browser/PDF viewer | Explain a paper section and uncertainty | READ | L | P |
| Reading PDFs | Study | Browser/PDF viewer | Navigate/explain selected pages | READ | L | P |
| Creating notes | Study | Docs/Word/notes app | Create a user-reviewed note draft | DOC | M | P |
| Flashcards | Study | Approved study tool | Draft cards from user-selected material | DOC | M | P |
| Citation tools | Research | Approved citation app | Organize a visible reference with source checking | DOC | M | P |
| Charts and tables | Study | PDF/Sheets | Interpret axes, units and cells | READ | L | P |
| Assignment preparation | Study | Docs/Word | Plan and understand own work, not submit automatically | DOC | M | P |
| Presentation preparation | Study | PowerPoint/Slides | Prepare and review slides | DOC | M | P |
| Learning unfamiliar software | Understand | Approved app pack | Learn one visible action at a time | READ | L | P |

## Business and professional tasks

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Invoices | Document | Word/Excel | Format a draft invoice; no payment or transaction | DOC | M | P |
| Reports | Document | Word/Docs | Assemble a user-reviewed report | DOC | M | P |
| Proposals | Document | Word/Docs | Draft/format a proposal; no legal submission | DOC | M | P |
| Resumes | Document | Word/Docs/Canva | Format a resume with private details hidden in context | DOC | M | P |
| Presentations | Presentation | PowerPoint/Slides | Prepare business slides | DOC | M | P |
| Project-management tools | Organize | Approved project app | Update an ordinary task after scope review | SET | M | P |
| File organization | Organize | File Explorer | Organize named work files safely | DOC | H | P |
| Meeting notes | Document | Docs/Word | Format provided notes; no passive recording | DOC | M | P |
| CRM guidance | Business workflow | Named future CRM pack | Explain approved nonsensitive workflow | NAV | M | F |
| Social-media content preparation | Content | Canva/Docs | Prepare drafts, no automatic posting | DESIGN | M | P |

## Communication and content

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Email setup | Setup | Approved mail app | Explain settings; credentials entered privately | SECRET | M | P |
| Email formatting | Content | Approved mail app | Format a draft; explicit confirmation before send guidance | SEND | H | P |
| Newsletters | Content | Approved newsletter tool | Draft and preview audience/content; confirm final publish/send | SEND | H | P |
| Professional documents | Document | Word/Docs | Format a user-reviewed professional draft | DOC | M | P |
| Captions | Content | Docs/approved dashboard | Prepare caption text for review | DOC | M | P |
| Audio editing | Edit media | Approved audio app | Explain basic edit/export controls | DESIGN | M | P |
| Content-upload guidance | Content | Approved dashboard | Review file/destination before user upload/submission | SEND | H | P |
| Publishing-dashboard guidance | Content | Approved dashboard | Preview visibility and confirm final publication instruction | SEND | H | P |

The Guide must not send, publish, submit or communicate externally without explicit confirmation; in MVP it has **no execution capability at all**. Post-MVP app support alone does not add one.

## AI-tool guidance

| Task name | Category | Application | User goal | Profile | Risk | Release |
|---|---|---|---|---|---|---|
| Installing AI tools | Setup | Browser/terminal | Follow official bounded developer-tool setup | SET | M | M |
| Setting up API keys | Setup | VS Code/terminal | Explain placeholder/env storage; private value entry outside Guide | SECRET | M | M |
| Understanding API keys | Understand | Browser/VS Code | Explain purpose, secrecy and usage without revealing values | READ | L | M |
| Prompt creation | Understand | Approved AI tool | Draft a clear bounded prompt | READ | L | P |
| Uploading files | AI workflow | Approved AI tool | Review data/destination before external file submission | SEND | H | P |
| AI-tool configuration | Setup | Approved AI tool | Explain ordinary settings with no security changes | SET | M | P |
| Model settings | Understand | Approved AI tool | Explain visible options and tradeoffs | READ | L | P |
| Usage limits | Understand | Browser | Interpret visible quota/limit message without purchase | READ | L | M |
| Connecting services | Setup | Approved AI tool | Explain non-secret integration; credential work private | SECRET | M | P |
| Troubleshooting AI tools | Debug | Browser/terminal | Diagnose visible local/network/config error | ERR | M | M |
| Using AI coding assistants responsibly | Understand | VS Code/browser | Review suggestions, inspect changes and test manually | CODE | L | M |

## Capability matrix

| Capability | MVP | Post-MVP / future boundary |
|---|---|---|
| Explain | Yes, visible/supplied context and uncertainty | Additional domains/providers after tests |
| Highlight | Yes, image-viewer boxes and fresh native mapped marker | Additional apps after geometry/vision fixtures |
| Read | User-supplied text/redacted images only; scoped local metadata for privacy | Explicit file/document access requires separate consent/API ADR |
| Suggest | One scoped action, safety-reviewed | Broader workflows retain same gate |
| Ask user to perform | Yes, supported low-risk actions and specifically confirmed allowed changes | New apps require app pack; high-risk blocks remain |
| Verify | Visible objective evidence or explicit self-report labeled separately | Additional app/verifier adapters; no unsupported hidden-state claims |
| Execute with confirmation | **No** shell, mouse, keyboard, file or external action execution | Requires new product authorization, ADR, sandbox and independent security review; not committed |
| Never execute | Banking/payment, CAPTCHA bypass, credential access, unauthorized monitoring, covert communication, arbitrary privilege/security changes | Remains forbidden product behavior unless explicit future policy review; no agent may infer an exception |

## Dependencies, assumptions, decisions and traceability

Profiles assume cropped non-sensitive context and user-controlled files/actions. D07 pins actual app versions/locales; D05 calibrates per-profile verifiers; D01 governs provider knowledge and source use. SEC-03/06/07/08/09 applies to every row. Example: “Help with Excel formulas” receives an honest post-MVP limitation in the initial release, not an enabled Excel overlay. R24/R25/R29 → F24/F25/F29 → T24/T25/T29 in [17](17-traceability-matrix.md). Expansion never weakens the six-category MVP contract silently.
