"""Small hosted BYOK service. Does not expose the unfinished saved-task backend.

One process/replica. Plans and connection grants are transient; encrypted keys
and per-account daily request counts live in PostgreSQL. No media storage.
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import SupabaseVerifier
from app.cloud import Connections, expire_connections
from app.cloud import router as cloud_router
from app.config import Settings
from app.database import make_database
from app.errors import GuideError
from app.personal_flow import router as flow_router
from app.personal_store import AccountKeys
from app.providers.registry import default_registry


def validate_hosted(settings: Settings) -> None:
    if not settings.supabase_url.startswith("https://") or not settings.supabase_url.endswith(
        ".supabase.co"
    ):
        raise ValueError("Configure the Supabase project URL.")
    if not settings.credential_root or len(settings.credential_root.get_secret_value()) < 32:
        raise ValueError("Configure a separate random credential root of at least 32 characters.")
    if not settings.personal_allowed_users:
        raise ValueError("Configure the Supabase user IDs allowed to use this personal deployment.")
    for owner in settings.personal_allowed_users:
        UUID(owner)
    if settings.environment != "test":
        if not settings.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("Hosted keys require persistent PostgreSQL storage.")
        if not settings.allowed_origins or any(
            not origin.startswith("https://") or "*" in origin or origin.endswith("/")
            for origin in settings.allowed_origins
        ):
            raise ValueError("Set exact HTTPS website origins without trailing slashes.")


def create_personal_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    validate_hosted(settings)
    engine, sessions = make_database(settings)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(expire_connections(app))
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        for token in list(app.state.cloud_connections.items):
            app.state.cloud_connections.remove(token)
        await engine.dispose()

    app = FastAPI(title="Guider Personal", lifespan=lifespan)
    app.state.personal_hosted = True
    app.state.settings = settings
    app.state.engine, app.state.sessions = engine, sessions
    app.state.verifier = SupabaseVerifier(settings.supabase_url)
    app.state.providers = default_registry()
    app.state.cloud_connections = Connections()
    app.state.personal_keys = AccountKeys(
        sessions, settings.credential_root.get_secret_value(), settings.provider_daily_calls
    )

    def failure(error: GuideError) -> JSONResponse:
        return JSONResponse({"error": error.body}, status_code=error.status)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        try:
            if request.url.path != "/health":
                if request.headers.get("origin", "") not in settings.allowed_origins:
                    raise GuideError(403, "origin_refused", "Open your configured Guider website.")
                authorization = request.headers.get("authorization", "")
                if not authorization.startswith("Bearer "):
                    raise GuideError(401, "invalid_token", "Sign in to use your saved connections.")
                identity = await app.state.verifier.verify(authorization[7:])
                if identity.id not in settings.personal_allowed_users:
                    raise GuideError(
                        403, "account_not_allowed", "This account is not enabled for Guider."
                    )
                request.state.owner = identity.id
            maximum = (
                6 * 1024 * 1024 if request.url.path.endswith(("/frames", "/checks")) else 65536
            )
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > maximum:
                    raise GuideError(413, "payload_too_large", "Request too large.")
                chunks.append(chunk)
            request._body = b"".join(chunks)
            response = await call_next(request)
        except GuideError as error:
            response = failure(error)
        except Exception:
            response = failure(
                GuideError(503, "dependency_unavailable", "Guider could not complete this request.")
            )
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            }
        )
        return response

    @app.exception_handler(GuideError)
    async def guide_error(request, error):
        return failure(error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return failure(GuideError(422, "validation_failed", "Check the request fields."))

    @app.get("/health")
    async def health():
        return {"service": "guider-personal", "status": "ok"}

    app.include_router(cloud_router)
    app.include_router(flow_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Guide-Connection"],
    )
    return app
