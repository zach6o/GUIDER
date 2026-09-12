"""Ephemeral, loopback-only BYOK connector. Never accesses account data or storage."""

import asyncio
import base64
import binascii
import hashlib
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Header, Request
from pydantic import Field, SecretStr

from app.errors import GuideError
from app.media import normalize
from app.providers.base import MAX_IMAGE, MODEL, CheckInput, Guidance
from app.providers.openai import POLICY, OpenAIVision
from app.schemas import Schema

# Moved to app.providers in PR-1; re-exported so existing importers resolve unchanged.
__all__ = [
    "MAX_IMAGE",
    "MODEL",
    "POLICY",
    "CheckInput",
    "Connection",
    "Connections",
    "Guidance",
    "OpenAIVision",
    "expire_connections",
    "prepare_cloud_image",
    "router",
]


class ConnectInput(Schema):
    api_key: SecretStr = Field(min_length=20, max_length=512)
    model: MODEL = "gpt-4.1-mini"
    accepted_cloud_terms: Literal[True]


class ConnectOutput(Schema):
    connection_token: str
    model: MODEL
    expires_in_seconds: int


@dataclass
class Connection:
    key: SecretStr
    model: str
    expires: float
    epoch: int = 1
    calls: int = 0
    last_call: float = 0
    pending: asyncio.Task | None = None

    def cancel(self) -> None:
        self.epoch += 1
        if self.pending:
            self.pending.cancel()


@dataclass
class Connections:
    items: dict[str, Connection] = field(default_factory=dict)
    attempts: deque = field(default_factory=deque)

    def sweep(self) -> None:
        for token, connection in list(self.items.items()):
            if connection.expires <= time.monotonic():
                self.remove(token)

    def remove(self, token: str) -> None:
        connection = self.items.pop(token, None)
        if connection:
            connection.cancel()
            connection.key = SecretStr("")


router = APIRouter(prefix="/api/v1/local-guide", tags=["Personal cloud development"])


def local_only(request: Request) -> Connections:
    origin = request.headers.get("origin", "")
    origin_url = urlparse(origin)
    host = request.url.hostname
    if (
        request.app.state.settings.environment not in {"development", "test"}
        or request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
        or host not in {"localhost", "127.0.0.1", "::1"}
        or origin not in request.app.state.settings.allowed_origins
        or origin_url.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise GuideError(
            403, "local_only", "This connection is available only from your local Guider app."
        )
    registry = request.app.state.cloud_connections
    registry.sweep()
    return registry


def connection_for(request: Request, authorization: str) -> tuple[str, Connection]:
    registry = local_only(request)
    if not authorization.startswith("Bearer "):
        raise GuideError(401, "connection_expired", "Connect your OpenAI key to continue.")
    token = hashlib.sha256(authorization[7:].encode()).hexdigest()
    connection = registry.items.get(token)
    if not connection:
        raise GuideError(
            401, "connection_expired", "Your connection expired. Connect your key again."
        )
    return token, connection


@router.post("/connection", response_model=ConnectOutput)
async def connect(body: ConnectInput, request: Request) -> ConnectOutput:
    registry = local_only(request)
    now = time.monotonic()
    while registry.attempts and registry.attempts[0] < now - 60:
        registry.attempts.popleft()
    if len(registry.attempts) >= 10 or len(registry.items) >= 8:
        raise GuideError(429, "rate_limited", "Too many connections. Disconnect or wait a minute.")
    registry.attempts.append(now)
    await request.app.state.cloud_provider.validate(body.api_key, body.model)
    capability = secrets.token_urlsafe(32)
    registry.items[hashlib.sha256(capability.encode()).hexdigest()] = Connection(
        key=body.api_key,
        model=body.model,
        expires=time.monotonic() + 1800,
    )
    return ConnectOutput(
        connection_token=capability, model=body.model, expires_in_seconds=1800
    )


@router.delete("/connection", status_code=204)
async def disconnect(request: Request, authorization: Annotated[str, Header()] = ""):
    registry = local_only(request)
    # Idempotent: a previously cleared capability stays cleared.
    if authorization.startswith("Bearer "):
        registry.remove(hashlib.sha256(authorization[7:].encode()).hexdigest())


@router.post("/cancel", status_code=204)
async def cancel(request: Request, authorization: Annotated[str, Header()] = ""):
    _, connection = connection_for(request, authorization)
    connection.cancel()


def prepare_cloud_image(encoded: str) -> bytes:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise GuideError(422, "image_unreadable", "Could not read this frame.") from None
    if len(raw) > MAX_IMAGE:
        raise GuideError(413, "payload_too_large", "Crop this frame to less than 4 MiB.")
    clean = normalize(raw)
    if max(clean.width, clean.height) > 2560 or len(clean.pixels) > MAX_IMAGE:
        raise GuideError(
            413, "payload_too_large", "Use a smaller crop, at most 2,560 pixels per side."
        )
    return clean.pixels


@router.post("/checks", response_model=Guidance)
async def check(body: CheckInput, request: Request, authorization: Annotated[str, Header()] = ""):
    token, connection = connection_for(request, authorization)
    if connection.pending and not connection.pending.done():
        raise GuideError(409, "check_in_progress", "A screen check is already running.")
    if connection.calls >= 40 or time.monotonic() - connection.last_call < 2:
        raise GuideError(
            429, "rate_limited", "Wait briefly between checks. Connections allow up to 40 checks."
        )
    epoch = connection.epoch

    # Admission happens before decoding so concurrent requests cannot each reserve a call.
    async def perform():
        image = await asyncio.to_thread(prepare_cloud_image, body.image_base64)
        if connection.epoch != epoch:
            raise asyncio.CancelledError()
        return await request.app.state.cloud_provider.analyze(
            connection.key, connection.model, body, image
        )

    connection.calls += 1
    connection.last_call = time.monotonic()
    pending = asyncio.create_task(perform())
    connection.pending = pending
    try:
        result = await asyncio.wait_for(pending, timeout=50)
        if connection.epoch != epoch or token not in request.app.state.cloud_connections.items:
            raise GuideError(409, "check_canceled", "This screen check was canceled.")
        if connection.expires <= time.monotonic():
            request.app.state.cloud_connections.remove(token)
            raise GuideError(401, "connection_expired", "Connect your key again.")
        return result
    except asyncio.CancelledError:
        raise GuideError(409, "check_canceled", "This screen check was canceled.") from None
    except TimeoutError:
        raise GuideError(503, "check_timeout", "This check took too long. Try again.") from None
    finally:
        if connection.pending is pending:
            connection.pending = None


async def expire_connections(app) -> None:
    while True:
        app.state.cloud_connections.sweep()
        await asyncio.sleep(1)
