"""Reproducible synthetic authenticated history load; never calls a provider.

Run: uv run python -m scripts.load_test --requests 200 --concurrency 8
This measures local API overhead, not model latency or deployed capacity.
"""

import argparse
import asyncio
import json
import math
import time
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.models import Base, now


async def run(requests: int, concurrency: int) -> dict:
    with TemporaryDirectory(prefix="guider-load-") as directory:
        root = Path(directory)
        app = create_app(
            Settings(
                _env_file=None,
                environment="test",
                provider_id="",
                provider_api_key=None,
                database_url=f"sqlite+aiosqlite:///{root / 'load.db'}",
                storage_path=root / "media",
                supabase_url="https://fixture.supabase.co",
            ),
            start_worker=False,
        )
        private_key = ec.generate_private_key(ec.SECP256R1())
        app.state.verifier.keys.get_signing_key_from_jwt = lambda _: SimpleNamespace(
            key=private_key.public_key(),
        )
        token = jwt.encode(
            {
                "sub": str(uuid4()),
                "iss": "https://fixture.supabase.co/auth/v1",
                "aud": "authenticated",
                "role": "authenticated",
                "iat": now(),
                "exp": now() + timedelta(hours=1),
            },
            private_key,
            algorithm="ES256",
            headers={"kid": "synthetic-load"},
        )
        durations, failures = [], []
        gate = asyncio.Semaphore(concurrency)
        try:
            async with app.state.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {token}"},
            ) as client:
                # Create the identity before concurrent requests exercise reads.
                assert (await client.get("/api/v1/guide/sessions")).status_code == 200

                async def request():
                    async with gate:
                        started = time.perf_counter()
                        result = await client.get("/api/v1/guide/sessions")
                        durations.append((time.perf_counter() - started) * 1000)
                        if result.status_code != 200:
                            failures.append(result.status_code)

                started = time.perf_counter()
                await asyncio.gather(*(request() for _ in range(requests)))
                elapsed = time.perf_counter() - started
        finally:
            await app.state.engine.dispose()
        durations.sort()
        return {
            "scope": "synthetic ASGI + SQLite + signed JWT; no network or provider",
            "requests": requests,
            "concurrency": concurrency,
            "failures": len(failures),
            "status_codes": sorted(set(failures)),
            "elapsed_seconds": round(elapsed, 3),
            "requests_per_second": round(requests / elapsed, 2),
            "p50_ms": round(durations[math.ceil(requests * 0.5) - 1], 2),
            "p95_ms": round(durations[math.ceil(requests * 0.95) - 1], 2),
            "p99_ms": round(durations[math.ceil(requests * 0.99) - 1], 2),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-p95-ms", type=float, default=2000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.requests <= 10000 or not 1 <= args.concurrency <= 64:
        parser.error("Use 1–10000 requests and 1–64 concurrent requests.")
    report = asyncio.run(run(args.requests, args.concurrency))
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    raise SystemExit(1 if report["failures"] or report["p95_ms"] > args.max_p95_ms else 0)
