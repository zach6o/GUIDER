"""Credentials at rest.

A provider key is not ours, it spends the user's money, and in several cases it
reaches well beyond Guider. These tests hold the properties that make storing one
defensible: nothing readable in the row, nothing decryptable without the root,
nothing transferable between owners, and rotation that never decrypts the key
itself.
"""

import pytest
from pydantic import SecretStr

from app.crypto import (
    Sealed,
    fingerprint,
    key_id_for,
    open_sealed,
    rewrap,
    root_key,
    seal,
)
from app.errors import GuideError

ALICE = "54d332b0-9948-42c8-94dd-11a913c79719"
BOB = "f2bf182e-f619-492b-a1cc-c10cf660ca64"
KEY = SecretStr("sk-live-not-a-real-key-000000")


def root(secret: str = "development-root") -> bytes:
    return root_key(secret)


def test_a_credential_round_trips():
    sealed = seal(KEY, root(), ALICE)
    assert open_sealed(sealed, root(), ALICE).get_secret_value() == KEY.get_secret_value()


def test_nothing_readable_is_written_down():
    sealed = seal(KEY, root(), ALICE)
    blob = " ".join(sealed.as_dict().values())
    assert KEY.get_secret_value() not in blob
    assert "sk-live" not in blob


def test_the_same_credential_seals_differently_every_time():
    """Fresh data key and nonce per credential, so two identical keys do not
    produce identical rows and nothing can be matched by ciphertext."""
    first, second = seal(KEY, root(), ALICE), seal(KEY, root(), ALICE)
    assert first.ciphertext != second.ciphertext
    assert first.wrapped_key != second.wrapped_key


def test_the_wrong_root_reads_nothing():
    sealed = seal(KEY, root(), ALICE)
    with pytest.raises(GuideError) as raised:
        open_sealed(sealed, root("a different deployment"), ALICE)
    assert raised.value.body["code"] == "dependency_unavailable"


def test_a_row_moved_to_another_account_fails_rather_than_opening():
    """The owner is authenticated data, so a credential lifted into another
    account does not decrypt into somebody else's provider."""
    sealed = seal(KEY, root(), ALICE)
    with pytest.raises(GuideError):
        open_sealed(sealed, root(), BOB)


def test_tampering_is_refused():
    sealed = seal(KEY, root(), ALICE)
    version, nonce, body = sealed.ciphertext.split(".")
    flipped = body[:-2] + ("AA" if not body.endswith("AA") else "BB")
    with pytest.raises(GuideError):
        open_sealed(
            Sealed(f"{version}.{nonce}.{flipped}", sealed.wrapped_key, sealed.key_id),
            root(),
            ALICE,
        )


def test_every_failure_looks_the_same():
    """A caller that could tell a wrong key from tampered bytes from the wrong
    owner would be an oracle."""
    sealed = seal(KEY, root(), ALICE)
    messages = set()
    for attempt in (
        lambda: open_sealed(sealed, root("wrong"), ALICE),
        lambda: open_sealed(sealed, root(), BOB),
        lambda: open_sealed(Sealed("v1.AAAA.AAAA", sealed.wrapped_key, "x"), root(), ALICE),
    ):
        with pytest.raises(GuideError) as raised:
            attempt()
        messages.add(raised.value.body["message"])
    assert len(messages) == 1


def test_an_unconfigured_deployment_refuses_to_pretend():
    with pytest.raises(GuideError) as raised:
        root_key("")
    assert raised.value.body["code"] == "dependency_unavailable"


# --- rotation -------------------------------------------------------------


def test_rotation_moves_the_wrapper_and_leaves_the_credential_alone():
    old, new = root("old"), root("new")
    sealed = seal(KEY, old, ALICE)
    rotated = rewrap(sealed, old, new, ALICE)
    # The user's key was never decrypted to change roots: only the wrapper moved.
    assert rotated.ciphertext == sealed.ciphertext
    assert rotated.wrapped_key != sealed.wrapped_key
    assert rotated.key_id == key_id_for(new)
    assert open_sealed(rotated, new, ALICE).get_secret_value() == KEY.get_secret_value()


def test_the_old_root_stops_working_after_rotation():
    old, new = root("old"), root("new")
    rotated = rewrap(seal(KEY, old, ALICE), old, new, ALICE)
    with pytest.raises(GuideError):
        open_sealed(rotated, old, ALICE)


def test_a_key_id_names_the_root_without_revealing_it():
    secret = "development-root"
    identifier = key_id_for(root(secret))
    assert secret not in identifier
    assert identifier == key_id_for(root(secret))
    assert identifier != key_id_for(root("something else"))


# --- fingerprints ---------------------------------------------------------


def test_a_fingerprint_recognises_a_repeat_without_storing_the_key():
    assert fingerprint(KEY) == fingerprint(SecretStr(KEY.get_secret_value()))
    assert fingerprint(KEY) != fingerprint(SecretStr("sk-live-something-else"))
    assert KEY.get_secret_value() not in fingerprint(KEY)
