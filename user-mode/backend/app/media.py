import asyncio
import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.errors import GuideError

MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class NormalizedImage:
    pixels: bytes
    width: int
    height: int
    digest: str


def normalize(raw: bytes) -> NormalizedImage:
    if len(raw) > MAX_BYTES:
        raise GuideError(413, "payload_too_large", "Choose an image smaller than 10 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise GuideError(415, "unsupported_media_type", "Choose PNG, JPEG or WebP.")
                width, height = source.size
                if max(width, height) > 8192 or width * height > 20_000_000:
                    raise GuideError(413, "payload_too_large", "Crop the image to at most 20 MP.")
                if getattr(source, "n_frames", 1) != 1:
                    raise GuideError(415, "unsupported_media_type", "Choose a still image.")
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGB")
                clean = Image.new("RGB", oriented.size)
                clean.paste(oriented)
                output = io.BytesIO()
                clean.save(output, format="PNG")
                pixels = output.getvalue()
                if len(pixels) > MAX_BYTES:
                    raise GuideError(413, "payload_too_large", "Choose a smaller crop.")
                return NormalizedImage(
                    pixels,
                    clean.width,
                    clean.height,
                    hashlib.sha256(pixels).hexdigest(),
                )
    except GuideError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise GuideError(422, "image_unreadable", "This image could not be read safely.") from None


class PrivateStorage(Protocol):
    async def put(self, pixels: bytes) -> str: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class LocalPrivateStorage:
    """Development storage only. Never mounted as a static/public directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        return self.root / f"{UUID(key)}.png"

    async def put(self, pixels: bytes) -> str:
        key = str(uuid4())
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.path(key).write_bytes, pixels)
        return key

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self.path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.path(key).unlink, missing_ok=True)
