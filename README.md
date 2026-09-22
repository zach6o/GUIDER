# Guider

A visual guide for computer tasks. You share the context; Guider explains; you stay in control.

The development app includes a React/TypeScript workspace, an authenticated FastAPI screenshot API, and an interactive screen-guide demo with optional local window mirroring. The demo needs no API key and demonstrates floating hints, sample action detection and automatic progression. Saved tasks support configurable providers, encrypted account connections, editable plans, searchable history, exports and opt-in dictation. With no provider configured, saved tasks use an explicitly synthetic fixture. This is **not a production-ready MVP**.

For personal browser guidance with your own API key, see the [personal-use checklist](docs/user-mode-guide/25-personal-use-readiness.md). For the full product, see the [completion checklist](docs/user-mode-guide/23-completion-checklist.md). The [local deployment guide](docs/user-mode-guide/24-local-deployment-and-release.md) explains the options without assuming you already have cloud accounts.

## Run with npm or pnpm

Prerequisites: Node.js 22.12+, Python 3.13 and `uv` on PATH. From the repository root:

```powershell
npm install
npm start
```

Or use pnpm:

```powershell
pnpm install
pnpm start
```

Installation runs the root setup script: it uses the existing frontend `package-lock.json` with `npm ci` and backend `uv.lock` with `uv sync --locked`. Both root package managers use these same dependency locks; npm is bundled with Node. If lifecycle scripts are disabled, run `npm run setup` or `pnpm run setup` explicitly.

`start` applies database migrations and launches both services in one terminal. Open **http://127.0.0.1:5173/#live**. Press **Ctrl+C** to stop both. Ports 5173 and 8000 must be free. `npm run dev` / `pnpm dev` are aliases for the same launcher; `npm run build` / `pnpm build` build the web app, and `npm test` / `pnpm test` run web and backend unit tests. Backend source changes require a restart.

The **Demo walkthrough** opens first. Follow the floating **Click here** hints in the practice app: **Settings → Appearance → Dark theme → Save changes**. Each click changes the sample, shows a brief check, and automatically updates the next hint. Wrong clicks do not advance the guide. **Watch automatically** plays the sample actions for you; **Try it myself** returns control. **Pause guide**, **Resume guide** and **Replay demo** let you review the flow at your own pace. These actions affect only the practice app.

Choose **Mirror my window** to see the practice app and its hints as an overlay over a local mirrored preview, then **Resume guide**. Hints point to sample controls, not controls in your real window. The demo takes no screenshots or AI requests and does not analyze or control your actual window. **Change window** replaces the source; **Stop mirroring** returns to the sample desktop and pauses the guide. The fullscreen button previews the browser overlay at a larger size; Escape exits fullscreen. Hiding the page pauses the demo and stops mirroring.

For actual vision guidance, choose **AI screen guide**, choose OpenAI or Claude, enter your API key in the app, select a model and accept the cloud terms. Describe your goal, choose **Share a window**, then **Check screen**. Review the still, crop or hide private details, check the review box and choose **Send to OpenAI** or **Send to Claude**. Perform the suggested step yourself and check the updated screen when ready. You can add a question before sending, or **Cancel check** while keeping the local preview on. After canceling, capture and review a fresh frame.

This local workflow uses the default development configuration and does not require Supabase or an `.env` file. Use desktop Chrome or Edge and keep Guider visible beside the selected window. Hiding Guider stops sharing. The preview stays local; each cloud frame needs a separate review. Sharing expires after 15 minutes; the in-memory key connection expires after 30 minutes. **Disconnect & clear key** closes both. Enter the key only in the app's key field.

Provider integration has automated tests with simulated OpenAI responses; a real API-key/model call and the native browser picker still require a manual check. See [implementation status](docs/user-mode-guide/19-implementation-status.md) and [ADR-015](docs/user-mode-guide/adr/015-browser-observation-and-personal-cloud.md).

## Try the web app

Requires Node.js 22.12+ (validated here with 24.19.0).

```powershell
cd user-mode/web
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. With no Supabase configuration, the app runs an explicitly labeled demo in browser memory. Choose **Explore an example → Let’s figure it out → review the screenshot → Upload this image → Explain this screenshot**. Try numeric crop/hide controls, Undo, Delete, Pause, Stop, and task history. Refresh clears the demo. It makes no backend or vision calls.

## Connect saved screenshot tasks to Supabase

Requires Python 3.13 and uv. Run from `user-mode/backend`:

```powershell
uv sync --locked
Copy-Item .env.example .env
New-Item -ItemType Directory -Force .local
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Set `GUIDE_SUPABASE_URL` in `.env` to your Supabase project using asymmetric signing keys. There is no backend demo token or alternate identity provider. Without Supabase, authenticated API requests fail closed. Interactive API documentation is at **http://127.0.0.1:8000/docs**.

To connect the web app, copy `user-mode/web/.env.example` to `.env`, set the same `VITE_SUPABASE_URL` and its public `VITE_SUPABASE_PUBLISHABLE_KEY`, then restart Vite. Configure the Supabase email template to display `{{ .Token }}` for email OTP sign-in. No service-role or model keys belong in the web environment. Browser authentication uses memory storage; refreshing requires signing in again. Real Supabase email delivery has not been tested in this workspace.

The API stores normalized images outside its public routes and requires an owner JWT to read them. SQLite/local storage are development defaults; PostgreSQL is the intended deployment database. Only synthetic media should be used during this development phase. `GUIDE_ENVIRONMENT=production` intentionally refuses startup until the remaining gates are satisfied.

For saved-task AI, configure `GUIDE_PROVIDER_ID`, its model and key in the backend, or open **AI connections** after signing in to choose a connection for each purpose. Supported saved-task adapters are Claude, OpenRouter, Groq, DeepSeek, Ollama and LM Studio; model/role support still needs live validation. A remote account key can only be saved when `GUIDE_CREDENTIAL_ROOT` is configured. `GUIDE_MEDIA_ENCRYPTION_KEY` enables encryption for local stored images; migrate existing images with `python -m scripts.encrypt_media` before enabling it. Keep these secrets separate and backed up. Configuration errors fail explicitly instead of silently using the fixture.

## Validate

```powershell
cd user-mode/backend
uv run pytest -q
uv run ruff check app tests scripts migrations
uv run alembic check
uv run python -m scripts.export_contract
```

```powershell
cd user-mode/web
npm.cmd test
npm.cmd run build
npx.cmd playwright install chromium
npx.cmd playwright test
npm.cmd run test:integration
```

The screenshot fixture can be regenerated with `uv run python -m scripts.make_fixture` from the backend directory. Dependency versions are pinned in `uv.lock` and `package-lock.json`. Generated contracts cover implemented endpoints only.

## Repository map

- `user-mode/web`: workspace, preview/crop/masking, authenticated API adapter and local demo.
- `user-mode/web/src/LiveGuide.tsx`: local window preview and reviewed OpenAI frame guidance.
- `user-mode/backend`: Supabase JWT verification, async database models, migrations, private storage, operation worker, media expiry and tests.
- `user-mode/backend/app/cloud.py`: ephemeral loopback-only personal OpenAI connector.
- `user-mode/contracts`: checked-in OpenAPI 3.1 and component schemas.
- `user-mode/client/windows`: independently buildable WPF shell and synthetic PKCE primitives; native capture, real authentication and signed packaging remain open.
- `user-mode/deploy`: loopback-only Docker Compose preview with PostgreSQL and encrypted media volume.
- [Implementation status](docs/user-mode-guide/19-implementation-status.md): implemented scope, evidence and remaining phase gates.
- [Product specification](docs/user-mode-guide/README.md): normative MVP requirements, contracts and implementation order.

The frontend follows the [Vite setup requirements](https://vite.dev/guide/). JWT verification follows the project's asymmetric signing-key policy and [Supabase's verification guidance](https://supabase.com/docs/guides/auth/jwts).
