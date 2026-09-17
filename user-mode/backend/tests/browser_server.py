"""Loopback-only browser harness. Never imported by the application.

The browser uses signed synthetic identities; all API routes, authorization,
database transactions and background operations are the actual application.
Only the external JWKS lookup and provider are fixtures.
"""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import Settings
from app.main import create_app
from app.models import Base, now
from tests.conftest import ALICE


async def main() -> None:
    with TemporaryDirectory(prefix="guider-browser-") as directory:
        root = Path(directory)
        app = create_app(
            Settings(
                _env_file=None,
                environment="test",
                database_url=f"sqlite+aiosqlite:///{root / 'browser.db'}",
                storage_path=root / "media",
                supabase_url="https://fixture.supabase.co",
                allowed_origins=["http://127.0.0.1:5174"],
                credential_root="synthetic-browser-test-root",
            )
        )
        private_key = ec.generate_private_key(ec.SECP256R1())
        app.state.verifier.keys.get_signing_key_from_jwt = lambda _: SimpleNamespace(
            key=private_key.public_key(),
        )
        claims = {
            "sub": ALICE,
            "iss": "https://fixture.supabase.co/auth/v1",
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now(),
            "exp": now() + timedelta(hours=1),
        }

        def token(**overrides):
            return jwt.encode(
                {**claims, **overrides},
                private_key,
                algorithm="ES256",
                headers={"kid": "browser-fixture"},
            )

        auth = Path(".local/browser-auth.json")
        auth.parent.mkdir(exist_ok=True)
        auth.write_text(
            json.dumps(
                {
                    "access_token": token(),
                    "expired_token": token(exp=now() - timedelta(minutes=5)),
                    "user": {
                        "id": ALICE,
                        "aud": "authenticated",
                        "role": "authenticated",
                        "email": "browser@example.test",
                        "app_metadata": {},
                        "user_metadata": {},
                        "created_at": now().isoformat(),
                    },
                }
            ),
            encoding="utf-8",
        )
        async with app.state.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            await uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=8001,
                    access_log=False,
                )
            ).serve()
        finally:
            auth.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
