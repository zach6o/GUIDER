import os
from datetime import timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.models import Base, now

ALICE = "54d332b0-9948-42c8-94dd-11a913c79719"
BOB = "f2bf182e-f619-492b-a1cc-c10cf660ca64"


# Set GUIDE_TEST_DATABASE_URL to run the suite against PostgreSQL. SQLite is the
# default, but it ignores SELECT ... FOR UPDATE, so the engine's per-owner
# serialization is only genuinely exercised under PostgreSQL.
POSTGRES_URL = os.environ.get("GUIDE_TEST_DATABASE_URL", "")
on_postgres = pytest.mark.skipif(not POSTGRES_URL, reason="Needs GUIDE_TEST_DATABASE_URL")


@pytest.fixture
async def harness(tmp_path):
    settings = Settings(
        environment="test",
        database_url=POSTGRES_URL or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_path=tmp_path / "media",
        supabase_url="https://fixture.supabase.co",
    )
    app = create_app(settings, start_worker=False)
    private_key = ec.generate_private_key(ec.SECP256R1())
    # Replace only network key lookup; requests still exercise production JWT verification.
    app.state.verifier.keys.get_signing_key_from_jwt = lambda _: SimpleNamespace(
        key=private_key.public_key(),
    )

    def token(owner=ALICE, **overrides):
        claims = {
            "sub": owner,
            "iss": "https://fixture.supabase.co/auth/v1",
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now(),
            "exp": now() + timedelta(minutes=30),
        }
        claims.update(overrides)
        return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "fixture"})

    async with app.state.engine.begin() as connection:
        # A shared PostgreSQL database is reused between tests; start each one clean.
        if POSTGRES_URL:
            await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token()}"
        yield SimpleNamespace(app=app, client=client, token=token, root=tmp_path)
    await app.state.engine.dispose()
