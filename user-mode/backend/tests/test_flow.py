import io
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import func, select

from app import models as m
from app.config import Settings
from app.main import create_app
from app.provider import python_fixture
from app.worker import sweep, tick
from tests.conftest import BOB

PREFIX = "/api/v1/guide"


async def create(harness, goal="Why won't Python run?", key=None):
    return await harness.client.post(
        PREFIX + "/tasks",
        json={
            "goal": goal,
            "category": "debug",
            "application_key": "powershell",
        },
        headers={"Idempotency-Key": key or str(uuid4())},
    )


async def upload(harness, created, raw=None, **metadata):
    data = created.json()["data"]
    meta = {
        "source": "manual",
        "purpose": "error",
        "captured_at": m.now().isoformat(),
        "session_id": data["session"]["id"],
        "expected_version": data["session"]["state_version"],
        **metadata,
    }
    return await harness.client.post(
        PREFIX + f"/tasks/{data['task']['id']}/screenshots",
        files={"file": ("private-filename.png", raw or python_fixture(), "image/png")},
        data={"metadata": json.dumps(meta)},
        headers={"Idempotency-Key": str(uuid4())},
    )


async def analyze(harness, created, uploaded, key=None):
    data = uploaded.json()["data"]
    return await harness.client.post(
        PREFIX + f"/tasks/{created.json()['data']['task']['id']}/analyses",
        json={
            "session_id": data["session"]["id"],
            "expected_version": data["session"]["state_version"],
            "screenshot_ids": [data["screenshot"]["id"]],
            "question": "What happened?",
        },
        headers={"Idempotency-Key": key or str(uuid4())},
    )


async def test_create_retry_is_private_and_idempotent(harness):
    key = str(uuid4())
    first = await create(harness, key=key)
    assert first.status_code == 201, first.text
    data = first.json()["data"]
    assert data["session"]["state"] == "task_created"
    assert data["session"]["observation_mode"] == "screenshot_only"
    assert "owner_id" not in data["task"]
    assert (await create(harness, key=key)).json()["data"] == data
    conflict = await create(harness, goal="Different content", key=key)
    assert conflict.status_code == 409
    harness.client.headers["Authorization"] = f"Bearer {harness.token(BOB)}"
    foreign = await harness.client.get(PREFIX + f"/tasks/{data['task']['id']}")
    assert foreign.status_code == 404


async def test_fixture_flow_persists_and_deletion_scrubs_results(harness):
    created = await create(harness)
    uploaded = await upload(harness, created)
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()["data"]["screenshot"]
    content = await harness.client.get(PREFIX + f"/screenshots/{image['id']}/content")
    assert content.status_code == 200
    assert content.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(content.content)).info == {}
    key = str(uuid4())
    pending = await analyze(harness, created, uploaded, key)
    assert pending.status_code == 202, pending.text
    operation_id = pending.json()["data"]["operation_id"]
    assert (await analyze(harness, created, uploaded, key)).json()["data"] == pending.json()["data"]
    await tick(harness.app)
    result = await harness.client.get(PREFIX + f"/operations/{operation_id}")
    assert result.status_code == 200, result.text
    analysis = result.json()["data"]["result"]
    assert "ModuleNotFoundError" in analysis["explanation"]
    assert analysis["observations"][0]["bbox"]["width"] == 0.85
    assert len(list((harness.root / "media").glob("*.png"))) == 1
    deleted = await harness.client.delete(PREFIX + f"/screenshots/{image['id']}")
    assert deleted.status_code == 202, deleted.text
    assert deleted.json()["data"]["status"] == "purged"
    repeated = await harness.client.delete(PREFIX + f"/screenshots/{image['id']}")
    assert repeated.json()["data"] == deleted.json()["data"]
    assert not list((harness.root / "media").glob("*.png"))
    assert (
        await harness.client.get(PREFIX + f"/screenshots/{image['id']}/content")
    ).status_code == 410
    assert (await harness.client.get(PREFIX + f"/operations/{operation_id}")).json()["data"][
        "result"
    ] is None
    assert (await analyze(harness, created, uploaded, key)).status_code == 410
    async with harness.app.state.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(m.AnalysisRow)) == 0


async def test_cross_owner_and_cross_task_evidence_fail(harness):
    first = await create(harness)
    image = await upload(harness, first)
    second = await create(harness, "Another task")
    mismatch = await upload(harness, second, session_id=first.json()["data"]["session"]["id"])
    assert mismatch.status_code == 404
    mismatch_analysis = await analyze(harness, second, image)
    assert mismatch_analysis.status_code == 404
    screenshot_id = image.json()["data"]["screenshot"]["id"]
    harness.client.headers["Authorization"] = f"Bearer {harness.token(BOB)}"
    assert (
        await harness.client.get(PREFIX + f"/screenshots/{screenshot_id}/content")
    ).status_code == 404
    assert (
        await harness.client.delete(PREFIX + f"/screenshots/{screenshot_id}")
    ).status_code == 404


async def test_pause_wins_over_queued_analysis_and_allows_manual_explanation(harness):
    created = await create(harness)
    uploaded = await upload(harness, created)
    pending = await analyze(harness, created, uploaded)
    session_id = created.json()["data"]["session"]["id"]
    paused = await harness.client.post(
        PREFIX + f"/sessions/{session_id}/pause",
        json={"reason": "user", "expected_version": 1},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["state"] == "paused"
    await tick(harness.app)
    operation_id = pending.json()["data"]["operation_id"]
    assert (await harness.client.get(PREFIX + f"/operations/{operation_id}")).json()["data"][
        "status"
    ] == "canceled"
    new_upload = await upload(
        harness, created, expected_version=paused.json()["data"]["state_version"]
    )
    assert new_upload.status_code == 201
    assert new_upload.json()["data"]["session"]["state"] == "paused"
    await analyze(harness, created, new_upload)
    await tick(harness.app)
    state = await harness.client.get(PREFIX + f"/sessions/{session_id}")
    assert state.json()["data"]["state"] == "paused"


async def test_delete_before_worker_prevents_result(harness):
    created = await create(harness)
    uploaded = await upload(harness, created)
    pending = await analyze(harness, created, uploaded)
    image_id = uploaded.json()["data"]["screenshot"]["id"]
    await harness.client.delete(PREFIX + f"/screenshots/{image_id}")
    await tick(harness.app)
    operation = await harness.client.get(
        PREFIX + f"/operations/{pending.json()['data']['operation_id']}"
    )
    assert operation.json()["data"]["status"] == "canceled"
    assert operation.json()["data"]["result"] is None


async def test_stale_upload_and_observation_are_rejected(harness):
    created = await create(harness)
    assert (await upload(harness, created)).status_code == 201
    assert (await upload(harness, created)).status_code == 409
    assert (await upload(harness, created, source="observation")).status_code == 403


@pytest.mark.parametrize(
    "raw", [b"<svg><script>alert(1)</script></svg>", b"not an image", b"PK\x03\x04"]
)
async def test_malformed_images_leave_no_objects(harness, raw):
    created = await create(harness)
    response = await upload(harness, created, raw=raw)
    assert response.status_code in {415, 422}
    assert not list((harness.root / "media").glob("*"))
    assert "private-filename" not in response.text


async def test_expired_media_is_unreadable_then_purged(harness):
    created = await create(harness)
    uploaded = await upload(harness, created)
    image_id = uploaded.json()["data"]["screenshot"]["id"]
    async with harness.app.state.sessions() as db, db.begin():
        image = await db.get(m.ScreenshotRow, image_id)
        image.expires_at = m.now() - timedelta(seconds=1)
    assert (
        await harness.client.get(PREFIX + f"/screenshots/{image_id}/content")
    ).status_code == 410
    await sweep(harness.app)
    assert not list((harness.root / "media").glob("*"))


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.invalid/auth/v1"},
        {"aud": "service_role"},
        {"role": "service_role"},
        {"sub": "not-a-uuid"},
        {"exp": m.now() - timedelta(minutes=1)},
        {"nbf": m.now() + timedelta(minutes=5)},
    ],
)
async def test_invalid_jwt_claims_fail_closed(harness, claims):
    harness.client.headers["Authorization"] = f"Bearer {harness.token(**claims)}"
    response = await create(harness)
    assert response.status_code == 401


async def test_missing_auth_and_invalid_signature(harness):
    harness.client.headers.pop("Authorization")
    assert (await create(harness)).status_code == 401
    harness.client.headers["Authorization"] = "Bearer invalid.token.signature"
    assert (await create(harness)).status_code == 401


async def test_revoked_user_rejected_even_with_valid_token(harness):
    assert (await create(harness)).status_code == 201
    async with harness.app.state.sessions() as db, db.begin():
        user = await db.scalar(select(m.User))
        user.auth_revoked_before = m.now() + timedelta(seconds=1)
    assert (await create(harness)).status_code == 401


async def test_strict_validation_does_not_echo_secrets(harness):
    response = await harness.client.post(
        PREFIX + "/tasks",
        json={
            "goal": " ",
            "category": "banking",
            "application_key": "unknown",
            "owner_id": "secret-value-must-not-echo",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert "secret-value" not in response.text


def test_production_startup_is_gated():
    with pytest.raises(RuntimeError, match="Production is gated"):
        create_app(Settings(environment="production"))


async def test_replacement_purges_old_pixels_and_analysis(harness):
    created = await create(harness)
    uploaded = await upload(harness, created)
    pending = await analyze(harness, created, uploaded)
    await tick(harness.app)
    old_id = uploaded.json()["data"]["screenshot"]["id"]
    session_id = created.json()["data"]["session"]["id"]
    session = (await harness.client.get(PREFIX + f"/sessions/{session_id}")).json()["data"]
    replacement = await upload(harness, created, expected_version=session["state_version"],
                               replaces_screenshot_id=old_id)
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["data"]["screenshot"]["version"] == 2
    assert (await harness.client.get(PREFIX + f"/screenshots/{old_id}/content")).status_code == 410
    operation_id = pending.json()["data"]["operation_id"]
    operation = (await harness.client.get(PREFIX + f"/operations/{operation_id}")).json()["data"]
    assert operation["result"] is None
    assert len(list((harness.root / "media").glob("*.png"))) == 1
