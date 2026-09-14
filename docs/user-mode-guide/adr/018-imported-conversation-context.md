# ADR-018 · Imported conversation context

Date: 2026-09-12 · Status: **adopted** 2026-09-14; implemented in PR-17. New ground. Depends on [ADR-017](017-provider-role-abstraction.md). Does not alter [005](005-guide-not-control.md), [010](010-one-step-guidance.md) or [012](012-high-risk-action-gates.md); constrained by [09](../09-security-and-privacy.md) SEC-09 and [13](../13-ai-behavior-policy.md).

## Context

Users frequently ask ChatGPT, Claude or Gemini how to do something and receive a plan they then fail to execute, because the answer sits in a chat window and the work happens in another application. Guider's value is the execution layer, not another place to ask. Requiring users to restate a goal they have already refined elsewhere discards their context and makes Guider look like a competitor to the assistant they already use.

## Decision

Guider accepts an existing conversation as task context. In this scope the transport is **paste only**: the user copies a transcript into a field. No browser extension, OAuth connector, scraping, automated login or third-party account credential is introduced, and none may be added without a superseding ADR.

A `ConversationImporter` role, per [ADR-017](017-provider-role-abstraction.md), extracts a goal and a candidate step list from the pasted text. The result is a **draft plan** at `status=draft` that MUST be displayed for explicit confirmation before anything starts, exactly as a generated plan is under [010](010-one-step-guidance.md). An import MUST NOT create a confirmed plan, start a session, enable observation, select a provider or alter policy.

Imported text is **untrusted data** in precisely the sense of SEC-09 and [13](../13-ai-behavior-policy.md), identical to text read off a screenshot. Instructions embedded in a transcript — including text claiming to come from a system prompt, a developer or Guider itself — carry no authority. The deterministic guard vets the extracted goal and every extracted step before they become a draft plan; blocked categories under [012](012-high-risk-action-gates.md) stay blocked regardless of what the transcript asserts.

Imports are owner-scoped, at most 32 KiB, redacted at import, stored in the `imported_conversations` table under retention class H (30 days) with the existing deletion cascade. The raw transcript is stored once for provenance and is erased with its task. Secrets recognized at import are dropped, not stored.

## Alternatives considered

Browser extension reading the assistant's page: broad permissions over a site holding the user's full history, for a feature that paste already delivers. Official connectors first: each needs its own authorization, retention and review, and none is necessary to prove the value. Treating imported steps as a confirmed plan: removes the confirmation gate that [010](010-one-step-guidance.md) exists to provide, and would let pasted text drive guidance directly. Import as free-text goal only: discards the step structure the user already paid for.

## Consequences

Users continue from work they already did, and Guider positions as the execution layer rather than a replacement assistant. The attack surface is prompt injection through pasted text, which is the same surface as screenshot content and is handled by the same guard — but the volume of attacker-controllable text per request is much higher, so the 32 KiB cap and the mandatory confirmation step are load-bearing, not incidental. Imported plans will often be wrong for the user's actual screen; the replanner handles this as an ordinary anomaly rather than a special case. Provenance must be visible in the UI so a user can tell an imported plan from a generated one.

## Revisit conditions

A first-party connector is separately authorized with its own credential, retention and review model; imports become a significant injection vector in practice; or the 32 KiB cap proves too small for real transcripts. Never grant imported text authority over policy, scope or provider selection, and never skip confirmation for an imported plan.

## Assumptions, dependencies, security and open decisions

Assume the user is entitled to the transcript they paste and that transcripts contain no third-party data the user may not share. Depends on the planner, guard and plan-confirmation path. D06 must cover retention of imported third-party content. SEC-09/13/14 apply: untrusted context supplies no instructions, minimal audit and exact deletion, quotas on import size and rate. Example: a pasted Claude thread about installing Docker becomes a 9-step draft; the step that says "run this script from the internet" is blocked by the guard before the user ever sees it as an instruction.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R02/R05/R18 | F02/F05/F18; `POST /imports/conversations`; UX02/UX04 | SEC-09/13/14; T02/T05/T18; v2 phase 4 |

Master traceability: [17](../17-traceability-matrix.md).

## Evidence

Implemented in PR-17. `app/imports/` holds the redactor and the injection check, the `import` role
is served by the fixture parser and the Anthropic adapter, and `tests/test_imports.py` covers the
decision's load-bearing claims: an import produces a draft and confirms nothing; an instruction
hidden in a transcript never becomes a step, in the goal or in the plan; a restricted action is kept
and blocked so the user can see what was suggested; a pasted key never reaches the stored
transcript; and text with nothing to follow is refused rather than guessed at. The browser suite
covers the same ground from the user's side, including that the plan screen says where it came from.
