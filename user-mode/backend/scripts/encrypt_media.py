"""Offline local-media migration. Stop Guider before running; keys stay in environment.

Set GUIDE_MEDIA_ENCRYPTION_KEY to the new secret. For rotation, also set
GUIDE_OLD_MEDIA_ENCRYPTION_KEY. Run without --apply to validate every file first.
After --apply, restart with the new key. Keep old keys until backups have expired.
"""

import argparse
import os
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidTag

from app.config import Settings
from app.storage import MAGIC, EncryptedPrivateStorage


def migrate(root: Path, new_secret: str, old_secret: str | None = None, *, apply=False) -> int:
    if not new_secret.strip():
        raise ValueError("Set GUIDE_MEDIA_ENCRYPTION_KEY before migrating.")
    root = root.resolve()
    target = EncryptedPrivateStorage(root, new_secret)
    old = EncryptedPrivateStorage(root, old_secret) if old_secret else None
    files = sorted(root.glob("*.png"))

    def plaintext(path):
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError("Media paths must be regular files inside the configured root.")
        key = str(UUID(path.stem)).encode()
        body = path.read_bytes()
        if not body.startswith(MAGIC):
            return body, key, False
        nonce, ciphertext = body[len(MAGIC):len(MAGIC) + 12], body[len(MAGIC) + 12:]
        try:
            return target.cipher.decrypt(nonce, ciphertext, key), key, True
        except InvalidTag:
            if old is None:
                raise ValueError("An image needs the previous encryption key.") from None
            return old.cipher.decrypt(nonce, ciphertext, key), key, False

    # Validate every key/path before replacing anything. Each replacement is atomic;
    # a interrupted run accepts files under either root and can be rerun safely.
    for path in files:
        plaintext(path)
    if apply:
        for path in files:
            pixels, key, already = plaintext(path)
            if already:
                continue
            nonce = os.urandom(12)
            body = MAGIC + nonce + target.cipher.encrypt(nonce, pixels, key)
            temporary = path.with_suffix(".encrypting")
            try:
                with temporary.open("xb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = Settings()
    secret = config.media_encryption_key.get_secret_value() if config.media_encryption_key else ""
    count = migrate(config.storage_path, secret, os.getenv("GUIDE_OLD_MEDIA_ENCRYPTION_KEY"),
                    apply=args.apply)
    print(f"{'Encrypted' if args.apply else 'Validated'} {count} local images.")


if __name__ == "__main__":
    main()
