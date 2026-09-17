import asyncio
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from app.errors import GuideError

MAX_BYTES = 10 * 1024 * 1024
DECODERS = threading.BoundedSemaphore(2)


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
                oriented = ImageOps.exif_transpose(source)
                if source.info.get("icc_profile"):
                    oriented = ImageCms.profileToProfile(
                        oriented,
                        ImageCms.ImageCmsProfile(io.BytesIO(source.info["icc_profile"])),
                        ImageCms.createProfile("sRGB"),
                        outputMode="RGB",
                    )
                else:
                    oriented = oriented.convert("RGB")
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
        ImageCms.PyCMSError,
    ):
        raise GuideError(422, "image_unreadable", "This image could not be read safely.") from None


MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_FRAME_EDGE = 2560


def decode(raw: bytes) -> NormalizedImage:
    """Decode untrusted bytes outside the API with CPU, memory and wall-clock bounds."""
    if len(raw) > MAX_BYTES:
        raise GuideError(413, "payload_too_large", "Choose an image smaller than 10 MiB.")
    env = {
        name: os.environ[name]
        for name in ("SystemRoot", "WINDIR", "TEMP", "TMP")
        if name in os.environ
    }
    try:
        with DECODERS:
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("decoder_worker.py"))],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        if result.returncode == 2:
            failure = json.loads(result.stdout)
            raise GuideError(failure["status"], failure["code"], failure["message"])
        if result.returncode or len(result.stdout) > MAX_BYTES + 1024:
            raise ValueError("Decoder failed")
        header, pixels = result.stdout.split(b"\n", 1)
        dimensions = json.loads(header)
        return NormalizedImage(
            pixels, dimensions["width"], dimensions["height"], hashlib.sha256(pixels).hexdigest()
        )
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        raise GuideError(422, "image_unreadable", "This image could not be read safely.") from None


def prepare_frame(encoded: str) -> bytes:
    """Decode one observed frame. Bounded like every other image path, and the
    result is returned rather than stored: observation frames are never persisted."""
    import base64
    import binascii

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise GuideError(422, "image_unreadable", "Could not read this frame.") from None
    if len(raw) > MAX_FRAME_BYTES:
        raise GuideError(413, "payload_too_large", "Crop this frame to less than 4 MiB.")
    clean = decode(raw)
    if max(clean.width, clean.height) > MAX_FRAME_EDGE or len(clean.pixels) > MAX_FRAME_BYTES:
        raise GuideError(413, "payload_too_large", "Use at most 2,560 pixels per side.")
    return clean.pixels


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
