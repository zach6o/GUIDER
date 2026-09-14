# ADR-019 · Screen context as a first-class belief

Date: 2026-09-14 · Status: proposed for V2; extends [016](016-web-first-tiered-observation.md) with a
second observation role and a derived record. Does not alter [005](005-guide-not-control.md),
[010](010-one-step-guidance.md) or [012](012-high-risk-action-gates.md); constrained by
[09](../09-security-and-privacy.md) SEC-09 and [04](004-no-raw-video-storage.md).

## Context

The observer answers one question: is this step's success criterion satisfied? That is enough to
advance a plan and not enough to guide anyone. A guide that knows only "not yet" cannot tell the
user they are in the wrong application, cannot notice that a dialog is blocking them, cannot see
that they already did step four, and cannot point at anything — because it never formed an opinion
about what is on the screen at all.

The V2 product sentence requires that opinion. The risk is equally clear: an opinion about a screen
looks exactly like evidence about a step, and a system that blurs the two would undo what
[010](010-one-step-guidance.md) and the whole verification model exist to protect.

## Decision

Introduce **`ScreenContext`**: a derived, content-free belief about the shared window, produced by a
new `observe_context` provider role and vetted by the guard like every other provider result.

1. A `ScreenContext` is **never** a verification. It cannot set `verified`, cannot write
   `verified_at`, and cannot produce a `VerificationResult`. Advancing a step still requires the
   verification path, with its own confidence bands.
2. It is persisted as description, never as pixels: a stage, a digest, an application name, a short
   screen description and a redacted error string. Retention class H, seven days, joined to the
   deletion cascade.
3. It carries a **`context_digest`** — a hash of the fields a guide would act on. An unchanged
   digest means no reasoning call is made. This is the mechanism that makes continuous context
   affordable rather than a per-frame invoice.
4. Screen text is **untrusted input** in the SEC-09 sense. Text on a screen addressing the model has
   no authority; the guard's injection check extends to the context's own fields, and a control
   whose label asks for an action is dropped rather than offered.
5. The Context Engine proposes; the Guide Engine still decides and is still the only writer of
   session state.

## Alternatives considered

**Extend `ObserveResult` with more fields.** Cheapest change, and wrong: it would put a belief about
the screen inside the record that decides whether a step passed, which is precisely the blur this
ADR exists to prevent.

**Derive context in the browser from the DOM.** Only works for web pages inside the browser, and the
product's subject is other applications — terminals, editors, installers. It would also make the
frontend the author of what the backend believes.

**Run one expensive call per frame that both understands and instructs.** Simpler pipeline, and
economically impossible at twelve frames a minute; it also removes the natural place to say "nothing
changed, spend nothing".

## Consequences

A cheap model must be good enough at describing a screen for the digest to be stable. If it is not,
the digest thrashes and the cost model collapses — that is the load-bearing assumption of V2.1 and
its exit gate measures exactly it.

Context gives the product a new way to be wrong: it can now believe the user is further ahead than
they are. Skipping forward therefore asks the user, and the calibration instrument built for the
0.85 threshold covers the new stage classifications too.

## Revisit conditions

A stable digest proves unachievable with a cheap model; per-frame cost exceeds the session budget in
real use; a native accessibility API makes structured UI trees available, at which point vision
becomes the fallback rather than the source.

## Assumptions, dependencies, security and open decisions

Assume the shared window is the only surface described, that no frame is retained, and that no
provider is trusted to police its own output. Depends on [016](016-web-first-tiered-observation.md),
[017](017-provider-role-abstraction.md) and the guard. D01 resolves per provider for the new role;
D05 now covers stage classification as well as the advance threshold. SEC-09/10/13/14 apply.

| Requirement | Functional/API/UI | Security/test/phase |
|---|---|---|
| R06/R08/R10/R23 | F06/F08/F10; `POST /sessions/{id}/context` | SEC-09/10/13/14; T51/T52/T57/T58; V2.1–V2.2 |

Master traceability: [17](../17-traceability-matrix.md).
