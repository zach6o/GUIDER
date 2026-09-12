# ADR-005 · Guide instead of controlling the computer

Date: 2026-09-07 · Status: proposed implementation baseline.

## Context

The initial promise is one verified step with user agency. Giving an AI general input/shell/file tools expands harm and confuses consent with execution.

## Decision

MVP explains, highlights, suggests and verifies. Users perform all mouse, keyboard, shell, filesystem and external actions. No execution tool/API exists, even with confirmation. Confirmation gates allowed guidance for concrete actions, not hidden computer control.

## Alternatives considered

Unrestricted desktop agent: outside product scope. Tool execution with generic confirmation: too broad and not necessary. Read-only explanation without visual marker: underserves visual guidance.

## Consequences

Tasks may take more user actions, but action ownership and evidence are clear. Coding assistance uses small explained edits/tests, not automatic whole-project solutions. Internal “agents” are bounded roles.

## Revisit conditions

User explicitly authorizes a different product scope with a new execution/sandbox/confirmation ADR and release tests. No implied upgrade from adding app packs.

## Assumptions, dependencies, security and open decisions

Assume users operate their own applications. Depends on 09/10/12/13; no open decision authorizes execution. Example: Guide describes `python --version`; it does not run it.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R08/R17/R29 | F08/F17/F29; Instruction/ActionConfirmation; UX06/UX13 | SEC-07/08/15; T08/T17/T29; all |

Master traceability: [17](../17-traceability-matrix.md).
