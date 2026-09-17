# Local deployment and release evidence

## Use it without cloud accounts

From the repository root, run `npm install`, then `npm start`. Open
`http://127.0.0.1:5173/#live`. The practice walkthrough needs no account or key.
It demonstrates the guide using fixed examples. Saved accounts and real AI
answers require separate services; the app does not create or charge for them.

The browser demo supports plan editing/reordering, history filtering/export and
voice transcript review. Demo records live in memory and clear on refresh.
Authenticated task links reopen saved tasks after another sign-in. Watching
always starts off when a task is reopened.

## Optional local containers

Docker Desktop must be running. From `user-mode/backend`:

```powershell
uv run python -m scripts.setup_deployment
```

This creates `user-mode/deploy/.env` with separate random database, credential
and media secrets. It never prints or overwrites existing secrets. Keep this
ignored file private and back it up with the data. Losing encryption keys makes
the corresponding stored data unreadable.

From `user-mode/deploy`:

```powershell
docker compose up --build -d
docker compose logs --tail 50
docker compose down
```

To run the backend suite, including PostgreSQL concurrency checks, in isolated
test containers: `docker compose --profile checks run --build --rm checks`.
The `checks-db` service is a separate disposable database; tests do not use the
preview application's database. Stop the test services with
`docker compose --profile checks down`.

The web app is on `http://127.0.0.1:5173` and API on port 8000. PostgreSQL is
internal to the Compose network. Containers use named database/media volumes;
`down` preserves them. API and web run without root privileges. The web server
sends the shared CSP as an HTTP header. Build-time frontend Supabase settings
must match runtime policy settings; rebuild after changing them.

This is a **local development deployment**. Public exposure, managed storage,
KMS, restore testing, TLS, hosting and release certification are not supplied by
this Compose file. The production startup guard remains enabled.

The temporary personal-key screen connector checks the actual loopback peer.
Docker networking does not preserve that peer, so use the ordinary `npm start`
workflow for that connector. Local model endpoints likewise refer to the backend
machine/container, not automatically to the host PC.

## What the external services mean

| Service | Why it is needed | Configuration location |
|---|---|---|
| Supabase project | Sign-in and private saved accounts | Backend `GUIDE_SUPABASE_URL`; web `VITE_SUPABASE_URL` and public `VITE_SUPABASE_PUBLISHABLE_KEY` |
| AI provider account or a local model server | Actual AI explanations and guidance | Backend provider settings or the signed-in AI connections page; remote keys stay on the backend |
| Hosting, private storage and key management | A service that stays available beyond this PC | Not provisioned; deployment region, storage, key management and backups need a reviewed plan |
| Windows signing identity | Trusted installation of a native desktop client | Not configured; needed when the complete native client is ready to distribute |

None is required to run the practice walkthrough. Never put provider keys,
credential roots, media keys or database passwords into frontend `VITE_*`
variables. A browser's speech service is separate from the configured task AI;
its notice is shown before dictation and the text must be reviewed before use.

## Repeatable engineering checks

Backend, from `user-mode/backend`:

```powershell
uv run pytest -q
uv run ruff check app tests scripts migrations
uv run alembic upgrade head
uv run alembic check
uv run python -m scripts.export_contract
uv run python -m scripts.load_test --requests 200 --concurrency 8 --output .local/load-report.json
```

The load report measures signed-JWT/API/SQLite overhead with synthetic requests.
It creates and removes a temporary database, makes no provider calls and writes
no task content in its report. Its p95 threshold is a regression check, not a
capacity promise. PostgreSQL concurrency tests run in CI; locally, point
`GUIDE_TEST_DATABASE_URL` at a **disposable test database** because those tests
drop and recreate its application tables.

Web, from `user-mode/web`:

```powershell
npm test
npm run build
npm run test:browser
npm run test:integration
```

The integration suite runs the actual API and worker with signed synthetic JWTs.
Only Supabase delivery/JWKS and provider answers are fixtures. It verifies task
recovery, encrypted settings, expired sessions and sign-out failures. This does
not certify real Supabase email delivery or identity-provider integration.

Native checks, from the repository root:

```powershell
dotnet build user-mode/client/windows/Guider.Windows.csproj --configuration Release
dotnet run --project user-mode/client/windows-tests/Guider.NativeChecks.csproj --configuration Release
```

## Evidence needed before a public release

1. Real Supabase sign-in, token refresh, revocation and account lifecycle on a
   configured test project. Use test accounts and record the project/region and
   result without retaining tokens.
2. Reviewed provider/model/region and retention terms. With an authorized key,
   run `uv run python -m scripts.smoke_provider --spend-real-money --output
   .local/provider-smoke.json`. It sends synthetic text/images for six roles and
   costs provider usage. Passing the smoke script proves request/schema/guard
   compatibility, not guidance accuracy. Do not run it without a chosen account.
3. D05 guidance evaluation with an approved dataset: record correct instructions,
   false advances, interventions, latency and actual usage costs. Run the existing
   calibration report over approved pilot sessions and retain the dataset version.
4. Production private object storage/KMS, bounded decoding with OS access
   restrictions, durable task/account deletion and backup erasure, orphan recovery,
   distributed admission and crash-safe provider accounting. Local encrypted
   volumes and process resource limits are useful development controls; they do
   not certify these requirements.
5. Native PKCE integration, token handling, user-selected capture, protected-window
   handling, DPI/multi-monitor overlays, accessibility, installer signing and
   updates. The current shell and PKCE primitives are only the starting point.

For each supported application, record exact OS/application version, locale,
display scaling, scenario, expected result, observed result and reviewer. The
minimum manual matrix is VS Code, PowerShell/Windows Terminal, Chrome/Edge,
Git/GitHub, Python, JavaScript/TypeScript and basic Docker Desktop. No row is
certified by a simulated browser demo. Native capture additionally needs
permission refusal/revocation, minimized/closed/protected windows, screen lock,
multiple displays and keyboard/screen-reader checks.
