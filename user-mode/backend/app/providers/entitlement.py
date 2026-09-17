"""Where a credential comes from, and nothing else.

Premium access is often built as a second pipeline: one path that reads the
user's key, another that reads managed configuration. That is also the design
that guarantees the two will drift, because every future change has to be made
twice and only one of them is exercised by the tests a developer runs locally.

[ADR-021](../../../../docs/user-mode-guide/adr/021-managed-provider-mode.md)
refuses that. Entitlement changes exactly one thing — *where the credential comes
from* — and everything downstream is identical: the same adapters, the same
schema, the same guard, the same budgets, the same events. A managed session and
a personal-key session differ in which model answered and what it cost, and in
nothing else.

Three rules this module exists to hold:

**A managed credential is never owner data.** It is not returned by any route,
never appears in an export, never lands in a deletion receipt, and is not part of
the owner's deletion cascade. It is not theirs; it is ours, spent on their
behalf.

**Entitlement is read at resolution time.** A subscription that lapses mid-task
degrades to the owner's own bindings, and then to the fixture. It does not strand
a running session, because a guide that stopped working the moment a payment
failed would be punishing the user for an accounting event.

**Nothing here is on.** D01 has selected no provider for account mode and D02 has
provisioned no key management, so `managed_available()` answers False on every
deployment that exists today. The plumbing is written and tested; the switch is
not ours to throw.
"""

from dataclasses import dataclass

from pydantic import SecretStr

from app.config import Settings

# What an entitlement can be. `none` is not an error: it is the ordinary state of
# every deployment right now.
TIERS = ("none", "managed")


@dataclass(frozen=True)
class Credential:
    """One resolved credential, and where it came from.

    `source` exists so that everything downstream — usage accounting, exports,
    deletion — can ask the one question that actually matters about a key without
    inspecting entitlement logic a second time.
    """

    key: SecretStr | None
    provider_id: str
    model: str
    source: str  # "owner" | "managed" | "none"

    @property
    def is_managed(self) -> bool:
        return self.source == "managed"

    @property
    def belongs_to_owner(self) -> bool:
        """Whether this credential is the user's own — which is exactly the
        question an export or a deletion has to ask."""
        return self.source == "owner"


def managed_available(settings: Settings) -> bool:
    """Whether this deployment can offer managed access at all.

    Both halves are required, and neither is configured anywhere today: a
    provider selected under D01, and a credential-encryption root under D02. A
    deployment with one and not the other is misconfigured rather than
    half-enabled, so this answers False for both.
    """
    return bool(settings.managed_provider_id) and bool(settings.managed_provider_key) and bool(
        settings.credential_root
    )


def entitled(settings: Settings, tier: str) -> bool:
    """Whether this owner may draw on managed access right now.

    Read at resolution time rather than cached on the session: a lapse degrades
    the next call, not the running guide.
    """
    return tier == "managed" and managed_available(settings)


def resolve(
    settings: Settings,
    tier: str,
    owner_key: SecretStr | None = None,
    owner_provider: str = "",
    owner_model: str = "",
) -> Credential:
    """The credential this call should use.

    Order is the whole rule, and it is written as a fall-through rather than a
    branch: managed when entitled and available, then the owner's own binding,
    then nothing — which the registry answers by resolving to the fixture and
    reaching no network at all.
    """
    if entitled(settings, tier):
        return Credential(
            key=settings.managed_provider_key,
            provider_id=settings.managed_provider_id,
            model=settings.managed_provider_model,
            source="managed",
        )
    if owner_key is not None and owner_provider:
        return Credential(
            key=owner_key, provider_id=owner_provider, model=owner_model, source="owner"
        )
    return Credential(key=None, provider_id="", model="", source="none")
