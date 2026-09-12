# ADR-008 · Supabase Auth remains the identity provider

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

The user requires Supabase unless code proves an approved alternative. No auth code or alternative decision exists in the empty repository. Identity must later fit Kurukul's owner boundaries.

## Decision

Use Supabase Auth for web and Windows login. Backend verifies JWT signature/project/issuer/audience/expiry and independently enforces owner/device/revocation policy. No Clerk, duplicate password database or client service-role key. Native uses system-browser PKCE with protected tokens; device credential supplements JWT, never replaces it.

## Alternatives considered

Clerk/another auth provider: violates requested baseline without evidence. Custom passwords: unnecessary security burden. Trust decoded client JWT: insufficient verification. Shared backend API key: no individual owner isolation.

## Consequences

Supabase configuration and auth tests are prerequisites. Local JWT verification does not guarantee instantaneous remote revocation; Guide adds application revocation and bounded identity liveness checks per 09.

## Revisit conditions

Only an explicit approved platform identity migration with compatibility, security and owner-ID mapping can supersede this decision. A provider preference is insufficient.

## Assumptions, dependencies, security and open decisions

Depends on 06–09 and native PKCE test; D02 project/hosting unresolved. No integration is claimed existing. Example: a valid token for a different Supabase project is rejected.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R15/R19 | F15/F19; User/Device/all API auth; UX14 | SEC-01/02; T15/T19/T36; 1/3 |

Master traceability: [17](../17-traceability-matrix.md).
