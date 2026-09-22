"""Local personal keys, protected by the signed-in Windows user's DPAPI key.

Only encrypted bytes reach disk. No browser-readable key or fallback plaintext
store exists. Other platforms keep supporting temporary connections.
"""

import ctypes
import json
import os
import re
import sys
from pathlib import Path

from pydantic import SecretStr

from app.errors import GuideError


def protect(raw: bytes, *, decrypt: bool = False) -> bytes:
    if sys.platform != "win32":
        raise GuideError(503, "key_storage_unavailable", "Remembering keys requires Windows.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(Blob),
    ]
    function.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # UI_FORBIDDEN, deliberately NOT LOCAL_MACHINE: another Windows user cannot decrypt it.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise GuideError(503, "key_storage_unavailable", "Windows could not unlock this key.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class PersonalKeys:
    def __init__(self, root: Path):
        self.root = root

    @property
    def available(self) -> bool:
        return sys.platform == "win32"

    def path(self, provider: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", provider):
            raise GuideError(422, "provider_unavailable", "Choose a supported provider.")
        return self.root / f"{provider}.dpapi"

    def has(self, provider: str) -> bool:
        return self.path(provider).is_file()

    def save(self, provider: str, key: SecretStr) -> None:
        sealed = protect(json.dumps({"provider": provider, "key": key.get_secret_value()}).encode())
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.path(provider)
        temporary = destination.with_suffix(".tmp")
        try:
            temporary.write_bytes(sealed)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, provider: str) -> SecretStr:
        try:
            saved = json.loads(protect(self.path(provider).read_bytes(), decrypt=True))
            if saved["provider"] != provider or not 20 <= len(saved["key"]) <= 512:
                raise ValueError("Invalid stored credential")
            return SecretStr(saved["key"])
        except (OSError, ValueError, KeyError, TypeError):
            raise GuideError(
                404, "saved_key_unavailable", "Enter and save your API key again."
            ) from None

    def forget(self, provider: str) -> None:
        self.path(provider).unlink(missing_ok=True)
