"""Owner-scoped provider connections and content-free call accounting."""

import time
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, SecretStr
from sqlalchemy import delete, func, select

from app import models as m
from app.auth import Db, Owner
from app.crypto import Sealed, open_sealed, root_key, seal
from app.errors import GuideError
from app.guide.observation import stop as stop_watching
from app.providers.entitlement import entitled, resolve
from app.providers.registry import CATALOG, available, build_configured
from app.schemas import Envelope, Schema

EngineRole = Literal["analyze", "plan", "instruct", "observe", "observe_context", "import"]
router = APIRouter(prefix="/api/v1/guide/providers", tags=["providers"])


class BindingInput(Schema):
    role: EngineRole
    provider_id: str = Field(min_length=1, max_length=40)
    model: str = Field(max_length=120, default="")
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    accepted: Literal[True]


class BindingView(Schema):
    role: EngineRole
    provider_id: str
    model: str
    has_key: bool


class ProviderView(Schema):
    id: str
    name: str
    roles: list[str]
    models: list[str]
    local: bool


class SettingsView(Schema):
    providers: list[ProviderView]
    bindings: list[BindingView]
    encrypted_storage_available: bool
    default_provider: str
    daily_limit: int
    managed_provider: str | None = None


class UsageView(Schema):
    calls: int
    succeeded: int
    remaining: int


def view(row: m.ProviderBinding) -> BindingView:
    return BindingView(
        role=row.role, provider_id=row.provider_id, model=row.model, has_key=bool(row.sealed_key)
    )


def root(settings) -> bytes:
    return root_key(settings.credential_root.get_secret_value() if settings.credential_root else "")


async def invalidate_watching(db, owner_id: str, request_id: str) -> None:
    sessions = await db.scalars(
        select(m.GuideSession).where(
            m.GuideSession.owner_id == owner_id,
            m.GuideSession.observation_active.is_(True),
        )
    )
    for session in sessions:
        await stop_watching(db, session, "provider_changed", request_id)


@router.get("", response_model=Envelope[SettingsView])
async def settings(request: Request, db: Db, owner: Owner):
    config = request.app.state.settings
    rows = await db.scalars(select(m.ProviderBinding).where(m.ProviderBinding.owner_id == owner.id))
    return {
        "request_id": request.state.request_id,
        "data": SettingsView(
            providers=[
                ProviderView(
                    id=d.id,
                    name=d.display_name,
                    roles=sorted(d.roles - {"guide"}),
                    models=list(d.models),
                    local=d.local,
                )
                for d, _ in CATALOG.values()
            ],
            bindings=[view(row) for row in rows],
            encrypted_storage_available=bool(config.credential_root),
            default_provider=config.provider_id or "fixture",
            daily_limit=config.provider_daily_calls,
            managed_provider=(
                config.managed_provider_id if entitled(config, owner.provider_tier) else None
            ),
        ),
    }


@router.post("/bindings", response_model=Envelope[BindingView])
async def save_binding(body: BindingInput, request: Request, db: Db, owner: Owner):
    descriptor = available(body.provider_id, body.role)
    model = descriptor.model_or_default(body.model)
    row = await db.scalar(
        select(m.ProviderBinding).where(
            m.ProviderBinding.owner_id == owner.id,
            m.ProviderBinding.role == body.role,
        )
    )
    encrypted = None
    if not descriptor.local:
        if body.api_key and body.api_key.get_secret_value().strip():
            encrypted = seal(body.api_key, root(request.app.state.settings), owner.id).as_dict()
        elif row and row.provider_id == body.provider_id and row.sealed_key:
            encrypted = row.sealed_key
        else:
            raise GuideError(422, "key_required", "Enter a key for this connection.")
    if row is None:
        row = m.ProviderBinding(owner_id=owner.id, role=body.role)
        db.add(row)
    row.provider_id, row.model, row.sealed_key = body.provider_id, model, encrypted
    await invalidate_watching(db, owner.id, request.state.request_id)
    await db.flush()
    return {"request_id": request.state.request_id, "data": view(row)}


@router.delete("/bindings/{role}", response_model=Envelope[bool])
async def remove_binding(role: EngineRole, request: Request, db: Db, owner: Owner):
    await invalidate_watching(db, owner.id, request.state.request_id)
    await db.execute(
        delete(m.ProviderBinding).where(
            m.ProviderBinding.owner_id == owner.id,
            m.ProviderBinding.role == role,
        )
    )
    return {"request_id": request.state.request_id, "data": True}


@router.get("/usage", response_model=Envelope[UsageView])
async def usage(request: Request, db: Db, owner: Owner):
    rows = list(
        await db.scalars(
            select(m.ProviderUsage).where(
                m.ProviderUsage.owner_id == owner.id,
                m.ProviderUsage.created_at > m.now() - timedelta(days=1),
            )
        )
    )
    return {
        "request_id": request.state.request_id,
        "data": UsageView(
            calls=len(rows),
            succeeded=sum(row.succeeded for row in rows),
            remaining=max(0, request.app.state.settings.provider_daily_calls - len(rows)),
        ),
    }


class Metered:
    def __init__(self, adapter, db, owner_id, role, provider_id, source):
        self.adapter, self.db = adapter, db
        self.owner_id, self.role = owner_id, role
        self.provider_id, self.source = provider_id, source

    def __getattr__(self, name):
        method = getattr(self.adapter, name)

        async def call(*args, **kwargs):
            attempt = dict(
                id=m.new_id(),
                owner_id=self.owner_id,
                role=self.role,
                provider_id=self.provider_id,
                source=self.source,
                succeeded=False,
                created_at=m.now(),
                latency_ms=0,
            )
            row = m.ProviderUsage(**attempt)
            self.db.info.setdefault("provider_attempts", []).append(attempt)
            self.db.add(row)
            started = time.monotonic()
            try:
                result = await method(*args, **kwargs)
                row.succeeded = True
                attempt["succeeded"] = True
                return result
            finally:
                row.latency_ms = round((time.monotonic() - started) * 1000)
                attempt["latency_ms"] = row.latency_ms

        return call


async def for_owner(app, db, owner_id: str, role: EngineRole):
    config = app.state.settings
    user = await db.get(m.User, owner_id)
    row = await db.scalar(
        select(m.ProviderBinding).where(
            m.ProviderBinding.owner_id == owner_id,
            m.ProviderBinding.role == role,
        )
    )
    key = (
        open_sealed(Sealed(**row.sealed_key), root(config), owner_id)
        if (row and row.sealed_key and not entitled(config, user.provider_tier))
        else None
    )
    credential = resolve(
        config,
        user.provider_tier,
        key,
        row.provider_id if row else "",
        row.model if row else "",
    )
    provider_id = credential.provider_id
    if row and available(row.provider_id, role).local and not credential.is_managed:
        provider_id = row.provider_id
        adapter = build_configured(provider_id, role, model=row.model)
        source = "owner"
    elif provider_id:
        descriptor = available(provider_id, role)
        adapter = build_configured(
            provider_id,
            role,
            api_key=credential.key,
            model=descriptor.model_or_default(credential.model),
        )
        source = credential.source
    else:
        # Preserve injectable defaults for the deterministic integration suite.
        if role == "analyze":
            adapter = app.state.provider
        elif role in {"observe", "observe_context"}:
            adapter = (
                getattr(app.state, "context_observer", None) if role == "observe_context" else None
            ) or app.state.observer
        else:
            adapter = app.state.providers.select(role)
        provider_id = config.provider_id
        source = "deployment"
        if not provider_id:
            return adapter
    calls = await db.scalar(
        select(func.count())
        .select_from(m.ProviderUsage)
        .where(
            m.ProviderUsage.owner_id == owner_id,
            m.ProviderUsage.created_at > m.now() - timedelta(days=1),
        )
    )
    if calls >= config.provider_daily_calls:
        raise GuideError(429, "provider_budget_spent", "Your daily provider-call budget is spent.")
    return Metered(adapter, db, owner_id, role, provider_id, source)
