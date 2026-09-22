"""Actual hosted personal API; only Supabase key lookup and vendor transport are synthetic."""

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
from app.models import now
from app.personal_app import create_personal_app
from app.personal_store import PersonalBase
from app.personal_types import PersonalPlan
from app.providers.registry import OPENAI
from tests.conftest import ALICE
from tests.test_personal import PLAN, TICK


class SyntheticProvider:
    async def validate(self, key, model):
        pass

    async def personal(self, key, model, context, schema, image=None):
        return schema.model_validate(
            PLAN if schema is PersonalPlan else {**TICK, "step_complete": True}
        )


async def main():
    with TemporaryDirectory(prefix="guider-personal-browser-") as directory:
        app = create_personal_app(
            Settings(
                _env_file=None,
                environment="test",
                database_url=f"sqlite+aiosqlite:///{Path(directory) / 'test.db'}",
                supabase_url="https://fixture.supabase.co",
                credential_root="browser-test-root-" * 3,
                personal_allowed_users=[ALICE],
                allowed_origins=["http://127.0.0.1:5175"],
            )
        )
        key = ec.generate_private_key(ec.SECP256R1())
        app.state.verifier.keys.get_signing_key_from_jwt = lambda _: SimpleNamespace(
            key=key.public_key()
        )
        app.state.providers.register(OPENAI, SyntheticProvider)
        token = jwt.encode(
            {
                "sub": ALICE,
                "iss": "https://fixture.supabase.co/auth/v1",
                "aud": "authenticated",
                "role": "authenticated",
                "iat": now(),
                "exp": now() + timedelta(hours=1),
            },
            key,
            algorithm="ES256",
            headers={"kid": "test"},
        )
        async with app.state.engine.begin() as db:
            await db.run_sync(PersonalBase.metadata.create_all)
        auth = Path(".local/personal-browser-auth.json")
        auth.parent.mkdir(exist_ok=True)
        auth.write_text(
            json.dumps(
                {
                    "access_token": token,
                    "user": {
                        "id": ALICE,
                        "aud": "authenticated",
                        "role": "authenticated",
                        "email": "personal@example.test",
                        "app_metadata": {},
                        "user_metadata": {},
                        "created_at": now().isoformat(),
                    },
                }
            )
        )
        try:
            await uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=8002, access_log=False)
            ).serve()
        finally:
            auth.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
