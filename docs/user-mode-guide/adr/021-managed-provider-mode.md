# ADR-021 · Managed credentials as a source, not a second pipeline

Date: 2026-09-14 · Status: proposed for V2; extends [017](017-provider-role-abstraction.md) and
generalises the personal-key connection of [015](015-browser-observation-and-personal-cloud.md).
Does not alter [005](005-guide-not-control.md), [008](008-supabase-auth.md) or
[012](012-high-risk-action-gates.md).

## Context

V2 offers two ways to pay for a model. A free user brings their own key and configures a provider
per role. A premium user configures nothing and uses Guider-managed infrastructure with better
models and higher limits.

The obvious implementation is two paths: a bring-your-own-key path that reads a credential row, and
a managed path that reads configuration. It is also the implementation that guarantees the two will
drift, because every future change has to be made twice and only one of them is exercised by the
tests a developer runs locally.

[017](017-provider-role-abstraction.md) already paid for the alternative. Roles resolve through one
registry, adapters are built per call, and a test reads the source and fails if anything outside
`app/providers/` names a provider.

## Decision

Managed access is **a credential source**, not a mode, a branch or a parallel pipeline.

1. `registry.select(role)` resolves as it does today. The only thing entitlement changes is *where
   the credential comes from*: an owner's encrypted binding row, or managed configuration.
2. Everything downstream is identical — the same adapters, the same schema, the same guard, the same
   budgets, the same events. A managed session and a personal-key session differ in which model
   answered and what it cost, and in nothing else.
3. A managed credential is **never owner data**: it is never returned by a route, never appears in
   an export, never lands in a deletion receipt, and is not part of the owner's deletion cascade.
4. Entitlement is read at resolution time, so a lapsed subscription degrades to the owner's own
   bindings, and then to the fixture — it does not strand a running session.
5. Every credential the *owner* supplies is envelope-encrypted at rest and returned by no route,
   in either mode.

## Alternatives considered

**A separate managed service.** Clean isolation, and it duplicates the guard, the budgets and the
event model — three things that must not diverge, because they are what keep answers safe.

**Managed keys injected as environment configuration read by adapters directly.** Convenient, and it
puts provider selection back inside adapters, undoing the abstraction ADR-017 exists to maintain and
breaking the source gate.

**Premium as a per-request flag from the client.** The client would then declare its own entitlement.
Not acceptable under SEC-01.

## Consequences

Entitlement becomes part of credential resolution, which is a small, testable surface — and the
place a bug would be expensive, so it gets its own test row (T56).

Usage accounting is now needed in both modes: a personal-key user wants to see what they spent, and
a managed user must be held to a limit. One tally serves both.

This decision does not decide *which* provider is managed. That is D01, per provider, and it stays
open; the hosting and key management this depends on are D02.

## Revisit conditions

A provider offers a delegated-credential model that removes the need to hold keys at all; managed
usage patterns diverge enough from personal-key usage that shared budgets stop making sense; a
regulatory requirement forces physical separation of managed traffic.

## Assumptions, dependencies, security and open decisions

Assume outbound HTTPS from the backend only, that no key is ever held by the frontend beyond the
request that sets it, and that key management is real rather than a local secret. Depends on
[017](017-provider-role-abstraction.md), [008](008-supabase-auth.md) for identity and D02 for KMS.
SEC-01/02/10/11/13 apply.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R15/R19/R23 | F15/F19/F23; `GET/PUT /providers/bindings`, `GET /providers/usage` | SEC-01/02/10/11/13; T55/T56; V2.4 and V2.6 |

Master traceability: [17](../17-traceability-matrix.md).
