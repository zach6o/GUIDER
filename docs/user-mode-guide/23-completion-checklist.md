# Guider completion work

For the narrower personal browser/API-key workflow selected on 2026-09-22, see
[25: Personal-use readiness](25-personal-use-readiness.md). The public/native
release gates below remain separate.

Started 2026-09-17. Authorized scope: finish the remaining items from the repository review, sequentially. This checklist records verified implementation separately from external release evidence.

1. [x] Provider selection is wired to saved-image analysis and all engine roles. Explicit misconfiguration fails instead of using a fixture. Adapter transport/contract tests pass; real service calls remain a release gate.
2. [x] Owner-scoped settings, encrypted per-role credentials, model validation, call accounting and managed entitlement resolution are wired. Changing connections revokes observation. Managed access is configuration/entitlement plumbing, not a billing or subscription product.
3. [ ] Production infrastructure remains open. Implemented locally: authenticated media encryption, offline migration/rotation, decoder subprocess with CPU/memory/time bounds, ICC conversion, retention cleanup, inaccessible pending image deletion with worker retries, and loopback-only PostgreSQL/container deployment. Production object storage/KMS, OS access isolation, task/account deletion outbox, orphan/backup recovery and distributed/crash-safe admission still need implementation and certification.
4. [x] Plan editing/reordering creates a new draft requiring confirmation; history search/filter/export, saved-task links and opt-in reviewed voice input are available. Guide controls retain their confirmation and evidence boundaries.
5. [x] Browser/API fixes, generated contracts, full browser scenarios and signed-JWT API/browser integration are in CI. CORS allows account deletion confirmation; observation routes admit their bounded frames; auth loss clears private UI/capture and discards late responses. Real Supabase email/session delivery remains untested.
6. [ ] Release scope is reconciled and repeatable load/provider tooling exists. The Windows shell builds and nine synthetic PKCE checks pass. Full native authentication/capture/overlay/signing, supported-app certification and measured live-provider guidance evaluation remain open.

External evidence required before claiming release readiness: a configured Supabase project; live provider calls using an authorized credential; hosting, storage/key-management and backup configuration; approved observation/privacy scope; measured guidance evaluation; Windows SDK, signed packaging and native capture certification where applicable. Do not replace these with passing fixture tests or remove the production guard to imply completion.

Baseline: 169 web tests, 62 browser scenarios, 487 SQLite backend tests passed; 12 PostgreSQL-dependent tests skipped locally. Web build, backend lint and migration consistency passed. No real-provider or Supabase session was exercised in the review.

Current engineering evidence and setup instructions are in [24](24-local-deployment-and-release.md). A synthetic local load run completed 200 requests at concurrency 8 with no failures (p95 437.56 ms); this is not a deployed service benchmark. Five authenticated browser/API scenarios pass. Both container images build, the local stack starts, and PostgreSQL migration parity passes. The native shell builds with .NET 10.0.401, zero warnings and errors, and nine PKCE checks pass. Final regression totals are recorded in [19](19-implementation-status.md).

The user has no known Supabase project, hosting selection, reviewed provider/model or signing configuration as of this session. Keep the usable local workflow available and the public-release guard closed; do not treat these missing accounts or unimplemented production/native requirements as completed work.
