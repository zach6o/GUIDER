import pytest

from app.errors import GuideError
from app.media import decode
from app.providers.fixture import python_fixture
from app.storage import EncryptedPrivateStorage
from scripts.encrypt_media import migrate


async def test_media_is_encrypted_round_trips_and_deletes(tmp_path):
    storage = EncryptedPrivateStorage(tmp_path, "test-key")
    original = python_fixture()
    key = await storage.put(original)
    assert storage.path(key).read_bytes() != original
    assert await storage.read(key) == original
    await storage.delete(key)
    assert not storage.path(key).exists()


async def test_media_cannot_be_swapped_or_read_with_another_key(tmp_path):
    storage = EncryptedPrivateStorage(tmp_path, "test-key")
    first = await storage.put(b"first")
    second = await storage.put(b"second")
    storage.path(second).write_bytes(storage.path(first).read_bytes())
    with pytest.raises(GuideError):
        await storage.read(second)
    with pytest.raises(GuideError):
        await EncryptedPrivateStorage(tmp_path, "wrong-key").read(first)


def test_isolated_decoder_accepts_pixels_and_rejects_invalid_data():
    clean = decode(python_fixture())
    assert (clean.width, clean.height) == (960, 400)
    with pytest.raises(GuideError) as error:
        decode(b"not an image")
    assert error.value.status == 422


async def test_offline_media_migration_rotation_and_retry(tmp_path):
    from app.media import LocalPrivateStorage
    plain = LocalPrivateStorage(tmp_path)
    key = await plain.put(b"private image")
    assert migrate(tmp_path, "first") == 1
    assert await plain.read(key) == b"private image"
    migrate(tmp_path, "first", apply=True)
    assert await EncryptedPrivateStorage(tmp_path, "first").read(key) == b"private image"
    migrate(tmp_path, "second", "first", apply=True)
    migrate(tmp_path, "second", "first", apply=True)
    assert await EncryptedPrivateStorage(tmp_path, "second").read(key) == b"private image"
    before = plain.path(key).read_bytes()
    with pytest.raises(ValueError):
        migrate(tmp_path, "wrong", apply=True)
    assert plain.path(key).read_bytes() == before
