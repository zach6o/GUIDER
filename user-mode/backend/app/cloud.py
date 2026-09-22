"""BYOK connections: loopback locally, account-bound in the personal hosted app."""

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
from app.guide.guard import POLICY, vet_guidance
from app.media import decode
from app.providers.base import MAX_IMAGE, CheckInput, Guidance
from app.schemas import Schema

# Moved to app.providers in PR-1; re-exported so existing importers resolve
# unchanged. The adapter itself is no longer among them: a connection stores
# which provider it belongs to and the registry builds it, so this module names
# no provider at all (ADR-017).
__all__ = [
    "MAX_IMAGE",
    "POLICY",
    "CheckInput",
    "Connection",
    "Connections",
    "Guidance",
    "expire_connections",
    "prepare_cloud_image",
    "router",
]


class ConnectInput(Schema):
    """A key, and which service it belongs to. The model list is the adapter's,
    checked by its capability descriptor rather than spelled out here."""

    api_key: SecretStr | None = Field(default=None, min_length=20, max_length=512)
    remember_key: bool = False
    use_saved_key: bool = False
    # Blank means "whichever adapter serves this role first", so a client that
    # does not care never has to know an id.
    provider: str = Field(default="", max_length=40)
    model: str = Field(default="", max_length=80)
    accepted_cloud_terms: Literal[True]


class ConnectOutput(Schema):
    connection_token: str
    provider: str
    display_name: str
    model: str
    expires_in_seconds: int


@dataclass
class Connection:
    key: SecretStr
    provider: str
    model: str
    expires: float
    owner: str = "local"
    epoch: int = 1
    calls: int = 0
    last_call: float = 0
    observation_times: deque = field(default_factory=deque)
    pending: asyncio.Task | None = None
    workflow: object | None = None

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
    if getattr(request.app.state, "personal_hosted", False):
        if (
            not getattr(request.state, "owner", None)
            or origin not in request.app.state.settings.allowed_origins
        ):
            raise GuideError(403, "origin_refused", "Open your configured Guider website.")
        request.app.state.cloud_connections.sweep()
        return request.app.state.cloud_connections
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
    if getattr(request.app.state, "personal_hosted", False):
        authorization = "Bearer " + request.headers.get("x-guide-connection", "")
    if not authorization.startswith("Bearer "):
        raise GuideError(401, "connection_expired", "Connect your provider key to continue.")
    token = hashlib.sha256(authorization[7:].encode()).hexdigest()
    connection = registry.items.get(token)
    if not connection or connection.owner != getattr(request.state, "owner", "local"):
        raise GuideError(
            401, "connection_expired", "Your connection expired. Connect your key again."
        )
    return token, connection


@router.post("/connection", response_model=ConnectOutput)
async def connect(body: ConnectInput, request: Request) -> ConnectOutput:
    registry = local_only(request)
    owner = getattr(request.state, "owner", "local")
    now = time.monotonic()
    while registry.attempts and registry.attempts[0] < now - 60:
        registry.attempts.popleft()
    attempt_limit = 100 if getattr(request.app.state, "personal_hosted", False) else 10
    if (
        len(registry.attempts) >= attempt_limit
        or len(registry.items) >= 200
        or sum(connection.owner == owner for connection in registry.items.values()) >= 8
    ):
        raise GuideError(429, "rate_limited", "Too many connections. Disconnect or wait a minute.")
    registry.attempts.append(now)
    providers = request.app.state.providers
    # The id came from the request, so it is checked the same way an unknown one
    # is: the registry refuses without saying which providers exist.
    descriptor = (
        providers.descriptor(body.provider, "guide")
        if body.provider
        else providers.first_for("guide")
    )
    model = descriptor.model_or_default(body.model)
    key = body.api_key
    if body.use_saved_key:
        if key is not None:
            raise GuideError(422, "validation_failed", "Choose a saved key or enter a new key.")
        key = await key_action(request, "read", descriptor.id)
    if key is None:
        raise GuideError(422, "validation_failed", "Enter an API key or use your saved key.")
    await admit_hosted(request)
    await providers.build(descriptor.id, "guide").validate(key, model)
    if body.remember_key:
        await key_action(request, "save", descriptor.id, key)
    capability = secrets.token_urlsafe(32)
    registry.items[hashlib.sha256(capability.encode()).hexdigest()] = Connection(
        key=key,
        provider=descriptor.id,
        model=model,
        expires=time.monotonic() + 1800,
        owner=owner,
    )
    return ConnectOutput(
        connection_token=capability,
        provider=descriptor.id,
        display_name=descriptor.display_name,
        model=model,
        expires_in_seconds=1800,
    )


@router.get("/saved-keys")
async def saved_keys(request: Request) -> dict:
    local_only(request)
    store = request.app.state.personal_keys
    providers = request.app.state.providers.for_role("guide")
    if getattr(request.app.state, "personal_hosted", False):
        return {"available": True, "providers": await store.providers(request.state.owner)}
    return {
        "available": store.available,
        "providers": [item.id for item in providers if await asyncio.to_thread(store.has, item.id)],
    }


@router.delete("/saved-keys/{provider}", status_code=204)
async def forget_key(provider: str, request: Request) -> None:
    registry = local_only(request)
    request.app.state.providers.descriptor(provider, "guide")
    await key_action(request, "forget", provider)
    for token, connection in list(registry.items.items()):
        if connection.provider == provider and connection.owner == getattr(
            request.state, "owner", "local"
        ):
            registry.remove(token)


async def key_action(request: Request, action: str, *args):
    method = getattr(request.app.state.personal_keys, action)
    if getattr(request.app.state, "personal_hosted", False):
        return await method(request.state.owner, *args)
    return await asyncio.to_thread(method, *args)


async def admit_hosted(request: Request) -> None:
    if getattr(request.app.state, "personal_hosted", False):
        await request.app.state.personal_keys.admit(request.state.owner)


@router.delete("/connection", status_code=204)
async def disconnect(request: Request, authorization: Annotated[str, Header()] = ""):
    registry = local_only(request)
    if getattr(request.app.state, "personal_hosted", False):
        authorization = "Bearer " + request.headers.get("x-guide-connection", "")
    # Idempotent: a previously cleared capability stays cleared.
    if authorization.startswith("Bearer "):
        token = hashlib.sha256(authorization[7:].encode()).hexdigest()
        found = registry.items.get(token)
        if found and found.owner == getattr(request.state, "owner", "local"):
            registry.remove(token)


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
    clean = decode(raw)
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
        await admit_hosted(request)
        image = await asyncio.to_thread(prepare_cloud_image, body.image_base64)
        if connection.epoch != epoch:
            raise asyncio.CancelledError()
        provider = request.app.state.providers.build(connection.provider, "guide")
        proposal = await provider.analyze(connection.key, connection.model, body, image)
        # The adapter cannot approve its own output; the guard decides.
        return vet_guidance(proposal)

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
