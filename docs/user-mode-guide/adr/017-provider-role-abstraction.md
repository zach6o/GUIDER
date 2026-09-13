# ADR-017 · Provider abstraction by bounded role

Date: 2026-09-12 · Status: proposed for v2; amends [014](014-initial-stack-and-contracts.md) and generalizes the OpenAI-specific connector in [015](015-browser-observation-and-personal-cloud.md). Resolves D01 into a per-provider gate rather than a single blocking choice. Does not alter [005](005-guide-not-control.md), [009](009-persist-task-state.md) or [012](012-high-risk-action-gates.md).

## Context

[12](../12-agent-responsibilities.md) already defines Planner, Context/Vision, Instruction, Verification and Explanation as bounded internal roles, and requires deterministic fixtures for each before provider integration. The implementation has two unrelated notions of a provider: `FixtureProvider` satisfies an `AnalysisProvider` Protocol on the account path, while `OpenAIVision` is a concrete class with OpenAI's Responses payload inline, wired directly into application state on the local path. Neither can express the v2 requirement that different roles use different providers — a cheap model observing, a capable model planning — or that a user brings their own provider. D01 has blocked all provider work as one decision, when the actual gates differ per provider and per mode.

## Decision

Providers implement bounded **roles**, not a single interface. Five Protocols: `VisionObserver`, `Planner`, `InstructionWriter`, `Verifier` and `ConversationImporter`. Each returns a validated structure, never free text.

Every adapter publishes a `CapabilityDescriptor`: `{id, display_name, roles, vision, structured_output, max_image_px, cost_tier, byok_only, local}`. The registry selects an adapter by **role and capability**, never by name. Provider-specific branching MUST NOT appear outside `app/providers/`; a name comparison anywhere else is a defect.

One internal JSON Schema per role is rendered into each provider dialect by a single normalizer — `json_schema` for OpenAI, a tool `input_schema` for Anthropic, `responseSchema` for Gemini, `format` for Ollama, and a prompt-plus-repair fallback for providers with none, capped at the single repair attempt [05](../05-session-state-machine.md) already permits. The existing conservative schema stripping moves into the normalizer and becomes per-dialect.

The deterministic Safety Guard runs **after** every provider result and **outside** every adapter. It applies to plans, instructions, observations and imported context alike. An adapter MUST NOT be able to suppress it, and a provider result is a proposal until schema, authorization, epoch and guard checks pass.

`FixtureProvider` implements every role deterministically and registers as provider `fixture`. It is the default in development and the reference for the provider matrix test.

Credential handling is unchanged in substance. BYOK connections stay loopback-only, hold the key as a secret in memory for at most 30 minutes, and are cleared on disconnect, restart or expiry. Account-mode providers use server-held credentials and never appear in the BYOK list. The `provider_connections` row stores `{provider_id, model, mode, created_at, expires_at}` and **never key material**. Browsers still MUST NOT call a provider directly (SEC-10). A `local: true` provider such as Ollama makes no network egress but receives no relaxation of guard, schema or budget rules.

D01 becomes per provider and per mode: a provider is reviewed before it may be used in account mode. BYOK remains available without that review, because the user supplies their own contract with the supplier.

## Alternatives considered

One provider interface for all roles: forces a single model to observe and plan, wasting capable-model tokens on boolean questions and preventing local observation. Provider-specific code paths in the orchestrator: exactly the coupling that makes a second provider a rewrite. Adapter chosen by configuration name only: cannot express that a provider lacks vision or structured output, so failures surface at request time. LangChain-style generic chains: hides schema enforcement and the guard boundary, both of which are load-bearing here.

## Consequences

Adding a provider becomes one file plus a matrix-test entry; the second adapter is the proof, and is scheduled deliberately for that reason. Structured-output quality varies by provider, so the fallback dialect will produce more repair attempts and more `invalid_answer` errors on weak providers; the descriptor's `structured_output` field lets the UI warn before selection. Per-role provider choice multiplies the configuration surface and the review matrix. Roles remain ordinary functions sharing adapters, as [12](../12-agent-responsibilities.md) assumes; no microservice is introduced.

## Revisit conditions

A role needs streaming or tool use that the Protocol shape cannot express; a reviewed account provider makes BYOK unnecessary; or a provider requires credential handling that in-memory loopback cannot satisfy. Never move key material into the database or the browser, and never let an adapter own the guard.

## Assumptions, dependencies, security and open decisions

Assume outbound HTTPS from the backend only, and that no provider is trusted to self-police output. Depends on [12](../12-agent-responsibilities.md), [13](../13-ai-behavior-policy.md) and [ADR-016](016-web-first-tiered-observation.md) for the observer role. D01 resolves per provider; D06 governs supplier retention terms per provider. SEC-09/10/11/14 apply: untrusted output validated, approved provider and no direct client-provider calls, TLS and least privilege, budgets. Example: Ollama observes locally while a reviewed cloud provider plans; the guard vets both identically.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R18/R19/R22/R23 | F18/F19/F22; `GET /providers`, `POST /providers/connections`; UX09 | SEC-09/10/11/14; T18/T22/T23; v2 phase 0 and 4 |

Master traceability: [17](../17-traceability-matrix.md).

## Evidence

A second adapter landed in PR-16 (`app/providers/anthropic.py`, four roles) and
`tests/test_provider_matrix.py` holds the decision to its claim two ways: identical fixtures go
through every adapter serving a role and must satisfy the same schema and the same guard, and the
source of `app/` outside `app/providers/` is read and must name no provider at all. Adding that
adapter required removing three leaks that predated it — an adapter imported by `app/cloud.py`, a
provider-named default model on the connect route, and provider-named settings keys — which is the
cost this decision exists to keep paying once rather than repeatedly.
