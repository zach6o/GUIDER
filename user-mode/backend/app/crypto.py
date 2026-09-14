"""Encrypting the credentials users hand us.

A provider key is the most dangerous thing this application stores. It is not
ours, it spends the user's money, and in several cases it reaches far beyond
Guider. So it is encrypted at rest with a per-owner data key, and the data key is
itself wrapped by a root key the application holds but never writes down beside
the ciphertext.

**This is envelope encryption without a managed KMS, and that is a real limit.**
Doc 22 records it: a root key living in configuration is better than plaintext in
a column and worse than a key management service, because anyone who can read the
configuration can read the keys. The shape here is deliberately the shape a KMS
drops into — `wrap` and `unwrap` are the only two functions that would change —
so closing D02 is a substitution rather than a rewrite.

What this does buy today, even with the weaker root: a database dump is not a
list of API keys, a backup restored elsewhere is useless without the root, and
rotating the root re-wraps every credential without touching the ciphertext the
user's key sits in.
"""

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

# AES-GCM through `cryptography`, which is already a dependency via PyJWT's
# crypto extra. No new dependency for the most security-sensitive code here.
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from app.errors import GuideError

NONCE_BYTES = 12
KEY_BYTES = 32
VERSION = "v1"


@dataclass(frozen=True)
class Sealed:
    """What is safe to write down: the ciphertext, the wrapped data key, and
    which root wrapped it. Nothing here is useful without the root."""

    ciphertext: str
    wrapped_key: str
    key_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "ciphertext": self.ciphertext,
            "wrapped_key": self.wrapped_key,
            "key_id": self.key_id,
        }


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


def root_key(secret: str) -> bytes:
    """A 32-byte root from whatever the configuration provides.

    Derived rather than used directly, so a short or non-random configured secret
    still produces a usable key — and so that the configured value is never the
    key itself, which makes rotating it a one-line change.
    """
    if not secret:
        raise GuideError(
            503,
            "dependency_unavailable",
            "Credential storage is not configured on this deployment.",
        )
    return hashlib.blake2b(secret.encode(), digest_size=KEY_BYTES).digest()


def key_id_for(root: bytes) -> str:
    """A short, non-reversible name for a root key.

    Stored beside the ciphertext so a rotation can tell which rows still need
    re-wrapping, without the row revealing anything about the key itself.
    """
    return hashlib.blake2b(root, digest_size=8).hexdigest()


def seal(plaintext: SecretStr, root: bytes, owner_id: str) -> Sealed:
    """Encrypt one credential under a fresh per-credential data key.

    The owner's id is authenticated data rather than a key input: two owners
    never share a data key anyway, and binding the ciphertext to the owner means
    a row moved to another account fails to decrypt instead of decrypting into
    someone else's provider.
    """
    data_key = os.urandom(KEY_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    body = AESGCM(data_key).encrypt(
        nonce, plaintext.get_secret_value().encode(), owner_id.encode()
    )

    wrap_nonce = os.urandom(NONCE_BYTES)
    wrapped = AESGCM(root).encrypt(wrap_nonce, data_key, owner_id.encode())
    return Sealed(
        ciphertext=f"{VERSION}.{_b64(nonce)}.{_b64(body)}",
        wrapped_key=f"{VERSION}.{_b64(wrap_nonce)}.{_b64(wrapped)}",
        key_id=key_id_for(root),
    )


def open_sealed(sealed: Sealed, root: bytes, owner_id: str) -> SecretStr:
    """Decrypt, or refuse.

    Every failure is the same refusal on purpose: a caller that could tell a
    wrong key from tampered ciphertext from the wrong owner would be an oracle.
    """
    try:
        version, nonce, wrapped = sealed.wrapped_key.split(".")
        if version != VERSION:
            raise ValueError("unknown version")
        data_key = AESGCM(root).decrypt(_unb64(nonce), _unb64(wrapped), owner_id.encode())

        version, body_nonce, body = sealed.ciphertext.split(".")
        if version != VERSION:
            raise ValueError("unknown version")
        plaintext = AESGCM(data_key).decrypt(
            _unb64(body_nonce), _unb64(body), owner_id.encode()
        )
    except (InvalidTag, ValueError, TypeError, IndexError):
        raise GuideError(
            503,
            "dependency_unavailable",
            "That stored credential could not be read. Enter it again.",
        ) from None
    return SecretStr(plaintext.decode())


def rewrap(sealed: Sealed, old_root: bytes, new_root: bytes, owner_id: str) -> Sealed:
    """Move a credential to a new root without touching the ciphertext.

    This is what makes rotation cheap, and it is the whole reason the data key
    exists rather than encrypting under the root directly: the user's key is
    never decrypted and re-encrypted to change roots.
    """
    version, nonce, wrapped = sealed.wrapped_key.split(".")
    data_key = AESGCM(old_root).decrypt(_unb64(nonce), _unb64(wrapped), owner_id.encode())
    fresh_nonce = os.urandom(NONCE_BYTES)
    rewrapped = AESGCM(new_root).encrypt(fresh_nonce, data_key, owner_id.encode())
    return Sealed(
        ciphertext=sealed.ciphertext,
        wrapped_key=f"{VERSION}.{_b64(fresh_nonce)}.{_b64(rewrapped)}",
        key_id=key_id_for(new_root),
    )


def fingerprint(plaintext: SecretStr) -> str:
    """A non-reversible tag for a credential, so the same key entered twice can
    be recognised without storing anything that could be replayed."""
    tag = hmac.new(b"guider-credential", plaintext.get_secret_value().encode(), "sha256")
    return tag.hexdigest()[:16]
