import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import database
from app.errors import GuideError
from app.models import User

bearer = HTTPBearer(auto_error=False)
Db = Annotated[AsyncSession, Depends(database)]


@dataclass(frozen=True)
class Identity:
    id: str
    issued_at: datetime


class SupabaseVerifier:
    def __init__(self, project_url: str):
        self.issuer = f"{project_url}/auth/v1"
        self.configured = bool(project_url)
        self.keys = (
            jwt.PyJWKClient(
                f"{self.issuer}/.well-known/jwks.json",
                lifespan=300,
                timeout=5,
                cache_keys=False,
            )
            if project_url
            else None
        )

    def _verify(self, token: str) -> Identity:
        if not self.configured:
            raise GuideError(503, "dependency_unavailable", "Supabase is not configured.")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"ES256", "RS256"} or not header.get("kid"):
                raise jwt.InvalidTokenError()
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=self.issuer,
                leeway=30,
                options={"require": ["exp", "iat", "sub", "iss", "aud", "role"]},
            )
            if claims["role"] != "authenticated":
                raise jwt.InvalidTokenError()
            return Identity(str(UUID(claims["sub"])), datetime.fromtimestamp(claims["iat"], UTC))
        except jwt.ExpiredSignatureError:
            raise GuideError(401, "token_expired", "Sign in again to continue.") from None
        except jwt.PyJWKClientConnectionError:
            raise GuideError(
                503,
                "dependency_unavailable",
                "Identity verification is unavailable.",
                retryable=True,
            ) from None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise GuideError(401, "invalid_token", "Sign in to continue.") from None

    async def verify(self, token: str) -> Identity:
        return await asyncio.to_thread(self._verify, token)


async def current_user(
    request: Request,
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise GuideError(401, "invalid_token", "Sign in to continue.")
    identity = await request.app.state.verifier.verify(credentials.credentials)
    # When this token was issued, for routes that require a recent sign-in rather
    # than merely a valid one. Account deletion is the only such route today.
    request.state.identity_issued_at = identity.issued_at
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    await db.execute(
        insert(User).values(id=identity.id).on_conflict_do_nothing(index_elements=["id"])
    )
    # Serialize this owner's mutations in PostgreSQL, including first-use idempotency races.
    user = await db.scalar(select(User).where(User.id == identity.id).with_for_update())
    if user.status != "active" or (
        user.auth_revoked_before and identity.issued_at <= user.auth_revoked_before
    ):
        raise GuideError(401, "invalid_token", "Sign in again to continue.")
    return user


Owner = Annotated[User, Depends(current_user)]
