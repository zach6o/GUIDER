"""Premium as a credential source, not a second pipeline.

The failure this guards against is architectural rather than behavioural: two
paths that drift, one of them exercised only in production. So these tests are
mostly about what entitlement is *not* allowed to change — and about the fact
that, on every deployment that exists today, it changes nothing at all because
managed access is not configured anywhere.
"""

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.providers.entitlement import (
    Credential,
    entitled,
    managed_available,
    resolve,
)

OWNER_KEY = SecretStr("owner-key")
MANAGED_KEY = SecretStr("managed-key")


def configured(**overrides) -> Settings:
    """A deployment where D01 and D02 are both closed. No such deployment exists;
    this is what one would look like."""
    return Settings(
        managed_provider_id="groq",
        managed_provider_key=MANAGED_KEY,
        managed_provider_model="llama-3.3-70b-versatile",
        credential_root=SecretStr("root"),
        **overrides,
    )


# --- nothing is on --------------------------------------------------------


def test_managed_access_is_unavailable_on_a_default_deployment():
    """D01 has selected no provider and D02 has provisioned no key management.
    The plumbing is written; the switch is not ours to throw."""
    assert managed_available(Settings()) is False
    assert entitled(Settings(), "managed") is False


@pytest.mark.parametrize(
    "half",
    [
        {"managed_provider_id": "groq"},
        {"managed_provider_key": MANAGED_KEY},
    ],
)
def test_half_a_configuration_is_misconfigured_rather_than_half_enabled(half):
    assert managed_available(Settings(**half)) is False


def test_an_entitled_owner_gets_nothing_where_it_is_not_configured():
    resolved = resolve(Settings(), "managed")
    assert resolved.source == "none"
    assert resolved.key is None


# --- the order ------------------------------------------------------------


def test_managed_is_preferred_where_it_is_both_entitled_and_available():
    resolved = resolve(configured(), "managed", owner_key=OWNER_KEY, owner_provider="deepseek")
    assert resolved.source == "managed"
    assert resolved.provider_id == "groq"


def test_an_unentitled_owner_falls_back_to_their_own_key():
    resolved = resolve(configured(), "none", owner_key=OWNER_KEY, owner_provider="deepseek")
    assert resolved.source == "owner"
    assert resolved.provider_id == "deepseek"
    assert resolved.key is OWNER_KEY


def test_a_lapse_degrades_rather_than_stranding_the_session():
    """Entitlement is read at resolution time. A payment failing mid-task moves
    the next call to the owner's own binding; it does not stop the guide."""
    settings = configured()
    during = resolve(settings, "managed", owner_key=OWNER_KEY, owner_provider="deepseek")
    after = resolve(settings, "none", owner_key=OWNER_KEY, owner_provider="deepseek")
    assert during.source == "managed"
    assert after.source == "owner"


def test_with_neither_there_is_nothing_and_that_is_not_an_error():
    """`none` resolves to no credential, which the registry answers by reaching
    for the fixture and touching no network."""
    assert resolve(Settings(), "none").source == "none"


# --- what a managed credential is not -------------------------------------


def test_a_managed_credential_is_not_the_owners():
    managed = resolve(configured(), "managed")
    owned = resolve(configured(), "none", owner_key=OWNER_KEY, owner_provider="deepseek")
    # The question an export or a deletion has to ask, answered in one place.
    assert managed.belongs_to_owner is False
    assert owned.belongs_to_owner is True
    assert managed.is_managed is True


def test_nothing_about_a_credential_is_printable():
    """A repr that leaked a key would put it in every log line that touched it."""
    managed = resolve(configured(), "managed")
    assert "managed-key" not in repr(managed)


def test_a_credential_carries_only_what_the_caller_needs():
    fields = set(Credential.__dataclass_fields__)
    # No entitlement object, no subscription, no account state: everything
    # downstream sees a key, who it is for, and where it came from.
    assert fields == {"key", "provider_id", "model", "source"}
