"""Authenticated encryption for local development media at rest."""

import asyncio
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto import root_key
from app.errors import GuideError
from app.media import LocalPrivateStorage

MAGIC = b"GUIDER-MEDIA-1\0"


class EncryptedPrivateStorage(LocalPrivateStorage):
    def __init__(self, root, secret: str):
        super().__init__(root)
        self.cipher = AESGCM(root_key("media:" + secret))

    async def put(self, pixels: bytes) -> str:
        from uuid import uuid4

        key = str(uuid4())
        nonce = os.urandom(12)
        body = MAGIC + nonce + self.cipher.encrypt(nonce, pixels, key.encode())
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.path(key).write_bytes, body)
        return key

    async def read(self, key: str) -> bytes:
        body = await super().read(key)
        if not body.startswith(MAGIC):
            raise GuideError(
                503, "storage_migration_required", "Stored images need encryption migration."
            )
        offset = len(MAGIC)
        try:
            return self.cipher.decrypt(
                body[offset : offset + 12], body[offset + 12 :], key.encode()
            )
        except (InvalidTag, ValueError):
            raise GuideError(
                503, "storage_unavailable", "This stored image could not be opened."
            ) from None
