import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api import router
from app.auth import SupabaseVerifier
from app.cloud import Connections, expire_connections
from app.cloud import router as cloud_router
from app.config import Settings
from app.database import make_database
from app.errors import GuideError
from app.guide.observation import SessionGate
from app.media import LocalPrivateStorage
from app.providers.registry import default_registry
from app.worker import run_worker


def create_app(settings: Settings | None = None, *, start_worker: bool = True) -> FastAPI:
    settings = settings or Settings()
    settings.check()
    engine, sessions = make_database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = asyncio.create_task(run_worker(app)) if start_worker else None
        cloud_expiry = asyncio.create_task(expire_connections(app))
        yield
        cloud_expiry.cancel()
        with suppress(asyncio.CancelledError):
            await cloud_expiry
        for token in list(app.state.cloud_connections.items):
            app.state.cloud_connections.remove(token)
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await engine.dispose()

    app = FastAPI(title="Guider Screenshot Help", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.verifier = SupabaseVerifier(settings.supabase_url)
    app.state.storage = LocalPrivateStorage(settings.storage_path)
    # Built from this app's own settings, so a configured provider is registered
    # for this process only. Selection stays by role and capability.
    registry = default_registry(settings)
    app.state.providers = registry
    # Selected by role, never by name: adding a provider does not touch this file.
    app.state.provider = registry.select("analyze")
    app.state.observer = registry.select("observe")
    app.state.observation = SessionGate()
    app.state.worker_healthy = True
    app.state.cloud_connections = Connections()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def transport(request: Request, call_next):
        request.state.request_id = str(uuid4())
        content_type = request.headers.get("content-type", "")
        limit = 11 * 1024 * 1024 if content_type.startswith("multipart/form-data") else 65536
        if request.url.path == "/api/v1/local-guide/checks":
            limit = 6 * 1024 * 1024
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return failure(request, GuideError(413, "payload_too_large", "Request too large."))
            chunks.append(chunk)
        request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # This API answers with JSON and with private image bytes, and nothing
        # else. It has no page to render, so the policy that suits it is the one
        # that permits nothing at all: a response that somehow reached a browser
        # as a document could then load nothing and be framed nowhere.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        # Content-free access metadata; no headers, query strings, file names or bodies.
        logging.getLogger("guider.audit").info(
            "request=%s method=%s status=%s",
            request.state.request_id,
            request.method,
            response.status_code,
        )
        return response

    def failure(request: Request, error: GuideError) -> JSONResponse:
        headers = {"Retry-After": "60"} if error.status == 429 else {}
        if error.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            {"error": error.body, "request_id": getattr(request.state, "request_id", str(uuid4()))},
            status_code=error.status,
            headers=headers,
        )

    @app.exception_handler(GuideError)
    async def guide_error(request: Request, error: GuideError):
        return failure(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _error):
        return failure(request, GuideError(422, "validation_failed", "Check the request fields."))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return failure(
            request, GuideError(error.status_code, "invalid_request", "Invalid request.")
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _error):
        return failure(
            request,
            GuideError(
                503,
                "dependency_unavailable",
                "The service is temporarily unavailable.",
                retryable=True,
            ),
        )

    app.include_router(router)
    app.include_router(cloud_router)
    return app


app = create_app()
