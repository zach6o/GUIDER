import io
from uuid import uuid4

from PIL import Image, ImageCms
from sqlalchemy import select

from app import models as m
from app.media import normalize
from app.worker import sweep
from tests.test_flow import PREFIX, create, upload
from tests.test_headers import assert_headers


async def test_failed_image_delete_is_inaccessible_and_retried(harness, monkeypatch):
    created = await create(harness)
    image = (await upload(harness, created)).json()["data"]["screenshot"]
    storage = harness.app.state.storage
    original = storage.delete

    async def unavailable(_key):
        raise OSError("Synthetic storage outage")

    monkeypatch.setattr(storage, "delete", unavailable)
    response = await harness.client.delete(PREFIX + f"/screenshots/{image['id']}")
    assert response.status_code == 202, response.text
    receipt = response.json()["data"]
    assert receipt["status"] == "purging"
    assert (
        await harness.client.get(PREFIX + f"/screenshots/{image['id']}/content")
    ).status_code == 410
    async with harness.app.state.sessions() as db:
        row = await db.get(m.ScreenshotRow, image["id"])
        key = row.object_key
        assert key and storage.path(key).exists()
    monkeypatch.setattr(storage, "delete", original)
    await sweep(harness.app)
    assert not storage.path(key).exists()
    async with harness.app.state.sessions() as db:
        job = await db.scalar(select(m.DeletionJob).where(m.DeletionJob.id == receipt["id"]))
        assert job.status == "purged"


async def test_frame_routes_accept_their_documented_body_size(harness):
    # Invalid body, but below the frame budget: the schema (422), not ingress
    # (413), rejects it. Ordinary JSON routes retain the smaller ingress bound.
    for suffix in ("observe", "context"):
        response = await harness.client.post(
            PREFIX + f"/sessions/{uuid4()}/{suffix}",
            json={"image_base64": "a" * 70_000},
        )
        assert response.status_code == 422
    response = await harness.client.post(PREFIX + "/tasks", content=b"a" * 70_000)
    assert response.status_code == 413
    assert_headers(response)


def test_icc_profile_is_converted_and_stripped():
    source = Image.new("RGB", (10, 10), (50, 100, 150))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    output = io.BytesIO()
    source.save(output, "PNG", icc_profile=profile)
    clean = Image.open(io.BytesIO(normalize(output.getvalue()).pixels))
    assert clean.info == {}
    assert clean.getpixel((0, 0)) == (50, 100, 150)
