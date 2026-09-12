# 18 · Repository inspection report

Inspection date: 2026-09-07. Workspace: `D:\PROJECTS\GUIDER`. Scope: the supplied local repository, including hidden filesystem entries and Git metadata inventory, before writing and again after documentation creation. No remote repository was supplied or configured. No source from another project was imported by this task.

## Verified evidence

| Inspection | Observed result | Interpretation |
|---|---|---|
| Get-Location / git rev-parse --show-toplevel | D:/PROJECTS/GUIDER | Correct supplied workspace |
| Get-ChildItem -Force before writing | `.git` only | No application/docs/config working-tree directories |
| rg --files before writing | No working-tree file output | No source files found; corroborated by hidden-file recursive inventory |
| git ls-files and git ls-files --stage | Empty output | No tracked files or index entries |
| git status --short --branch | `No commits yet on main` | Newly initialized unborn branch |
| git log -5 --oneline | Fatal: current branch main has no commits yet | No historical implementation to inspect |
| git remote and git remote -v | Empty output | No configured upstream to inspect |
| Recursive file inventory | `.git/config`, description, HEAD, standard sample hooks and info/exclude | Repository metadata only; hooks are samples, not product tooling |
| Workspace/ancestor AGENTS.md search | No AGENTS.md found at workspace, D:/PROJECTS or D:/ | No additional repository architecture instructions found |
| Final hidden-directory inventory | `.git/`, `docs/`, and a concurrently appearing `.claude/skills/` collection | Documentation added by this task; external tooling additions preserved and inspected separately |

The `.claude/skills/` collection was absent at initial inspection and present during final validation. At inventory it contained 313 files in 17 skill directories: brainstorming, canvas-design, code-reviewer, docx, frontend-design, mobile-design, react-best-practices, senior-architect, senior-backend, senior-frontend, senior-fullstack, senior-prompt-engineer, senior-security, skill-creator, ui-design-system, ui-ux-pro-max and webapp-testing. Files are skill instructions, reference rules, fonts/licenses, document schemas and support/scaffolding scripts; they are not an instantiated Guide web/backend/Windows application. They were not created, executed or modified by this documentation task. No product configuration or routes were inferred from examples inside them.

Git emitted a warning that the user's global ignore file could not be accessed. The hidden-file recursive inventory independently established the empty working tree; the warning does not prove a product feature or hide a verified source tree. No global settings, Git metadata, sample hooks or external directories were modified. Local machine SDK/package availability was not established as a product dependency inventory; pin/check tools during phase 0 coding.

## Existing implementation inventory

| Requested area | Verified state | Proposed destination/decision |
|---|---|---|
| Directories | Only `.git/` existed before this task | Future `user-mode/web`, `user-mode/backend`, `user-mode/client/windows`; docs now added |
| Frontend routes/components | None found | New web route inventory in 06; no legacy dashboard to retain |
| Backend routes/services | None found | New `/api/v1/guide` contracts in 07 |
| Database models/migrations | None found; no SQLAlchemy/SQLite/PostgreSQL code | Proposed entities/retention in 08; PostgreSQL + SQLAlchemy/Alembic ADR-014 |
| Authentication | No Supabase, JWT middleware or other auth code/config found | Supabase Auth required by user brief; not an existing integration |
| Environment variables/ports | No .env/example/config/manifests found | Proposed variables and ports in 06, not inherited contracts |
| Windows client | No C#/.NET/native/Electron/Tauri code or package found | Proposed WPF/capture design in 04/ADR-014 |
| Chat/guidance behavior | No chat, LLM, screenshot, voice, overlay or guidance implementation | Specification only; no claimed functioning chat route |
| LLM provider | None configured or imported | D01; no evidence for Claude or any other selected provider |
| Tests/CI | No tests, package scripts, CI workflows or fixtures | Proposed T01–T40 strategy in 16 |
| Deprecated/legacy routes | None found | Do not create fake aliases or deprecation migrations |
| Dependency manifests/lockfiles | None found | All framework/runtime/provider dependencies must be selected/pinned/installed later |
| Deployment/packaging | No Dockerfile, deployment config, Windows package/update feed | D02/D04 gates |

**Existing:** Git repository metadata, concurrent `.claude/skills/` tooling, and documentation created in this task. **Partially implemented product behavior:** none. **Proposed:** all product behavior and service contracts. **Future:** cross-mode integration and expansion explicitly labeled. **Deprecated:** none. Absence is established only for this workspace; an external Kurukul repository may exist but was not supplied and is not claimed inspected.

## Mismatches, contradictions and security gaps

There are no code-to-code contradictions to report because no product code exists. The possible directories, Supabase JWT code, SQLite/SQLAlchemy persistence, Claude integration, legacy chat routes, ports and migrations in the brief are **inspection hypotheses**, not observed facts. Treating them as existing would be the primary architecture mismatch.

Design tensions resolved in the documentation:

| Tension | Resolution |
|---|---|
| Broad domains versus narrow MVP | Complete taxonomy, explicit M/P/F release per task; six initial categories and named app packs |
| Guide “execution with confirmation” versus guidance-first | No MVP execution; confirmation gates user-performed modifying/external-action guidance only |
| Pause observation versus manual screenshots | Session pause revokes live grant; explicit uploads/questions remain possible without progression |
| Stopped UI versus required state list | Terminal state `completed`, outcome `stopped`; no extra `stopped` enum; overlays disappear |
| Done versus verification | CompletionClaim separate from VerificationResult; self-report labeled separately |
| Persisted recovery versus privacy | Redacted task content retained 30 days; screenshots 24 h; no grant/pointer automatically restored |
| Windows 10 requirement versus servicing | Compatibility target retained, production support gated D03; general support already ended |
| Phase 6 app expansion includes MVP apps | Phase 6a certifies initial apps; phase 6b separately expands domains |

Critical missing security foundations, not discovered exploitable code vulnerabilities: identity verification, owner authorization, native secure auth/device storage, consent/capture gates, provider review, media isolation/redaction/deletion, safe state/epoch handling, signing and tests. None are implemented. Visual sensitive-content detection and success verification are inherently fallible; production safety needs deterministic guards/manual alternatives and measured tests, not just a strong prompt.

## Recommended implementation order and protected decisions

Follow [15](15-mvp-implementation-plan.md): contracts/auth/media privacy → screenshot explanation → editable confirmed plan/manual verified loop → native auth/overlay → scoped live stills → voice/recovery → app certification → optional expansion. First coding slice: authenticated task creation and private screenshot analysis through a deterministic adapter, including real deletion and cross-owner tests. No broad implementation is included now.

Files/designs requiring ADR review before changing their contracts: 05 state vocabulary/epochs, 07 routes/auth/idempotency, 08 owner model/retention, 09 identity/consent/risk boundary, 06 service boundaries, and all accepted ADR decisions. Once implemented, corresponding migration history, auth middleware, client capture gate, API schemas, signing/update configuration and cross-mode interface must not be modified incompatibly without an ADR. Routine implementation and bug fixes inside those contracts do not require a new ADR. Never rewrite `.git/` as part of product work.

## Readiness and limitations

The repository is ready for **contract-first phase 0/1 implementation using synthetic data**, after the coding agent checks current versions/toolchain. It is not ready to run/deploy a product or process production screen/voice data. D01–D07 in README are named owner/gate decisions; provider/hosting/retention review precedes real data, Windows servicing/signing precedes distribution. No actual product tests, migrations, build or desktop verification could be run against absent code.

Final validation checks required files, relative links, R/F/T coverage, API/state/retention vocabulary and ADR sections. Task-authored changes are confined to 34 Markdown files under docs/user-mode-guide. Concurrent `.claude/skills/` additions were inventoried and preserved. No Guide application source, migrations, auth integration or product tests appeared during reinspection.

Automated documentation checks passed: all 18 numbered deliverables and both README files present; 14 ADRs contain the required decision sections; all 30 requirement mappings, 40 test definitions and 10 acceptance scenarios present; no broken relative links, mismatched Markdown table columns or unclosed code fences. Manual contract review reconciled capture-intent admission, exact pending-instruction confirmation, pause/cancel/restart timing, provider retry budgets and audit erasure ownership. This is documentation validation, not evidence that product security or behavior has been tested.

Assumptions: supplied workspace is the intended standalone repository, proposed defaults are design decisions, external Kurukul integration remains future. Security/dependencies: 06/09/15. Traceability R30/F30/T30 and all gap-related requirement rows in [17](17-traceability-matrix.md).
