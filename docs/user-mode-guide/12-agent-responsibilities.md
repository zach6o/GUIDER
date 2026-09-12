# 12 · Agent responsibilities

Status: proposed internal role design. “Agent” here means a bounded role coordinated inside User Mode backend, not a separately networked autonomous process. No agent implementation or Agent Zero integration exists in this repository.

## Responsibility map

| Role | Owns | Inputs → outputs | Prohibited responsibilities |
|---|---|---|---|
| Guide Orchestrator | Session state, scheduling, boundaries, safety enforcement, context requests, rechecks, retries and final summary | Authenticated command + current state → operation/validated event/instruction | Cannot delegate authorization/state mutation to LLM |
| Context/Vision Agent | Visible observations and uncertainty | Sanitized selected images + context schema → labels, boxes, missing context, confidence | Cannot infer offscreen controls, grant capture, execute or mark success |
| Task Planner | Bounded goal decomposition and success criteria | Goal, app scope, observations → 1–12 proposed steps and assumptions | Cannot approve its own plan or widen task/app scope silently |
| Instruction Agent | One action with location, rationale and fallback | Confirmed current step, verified observations, policy disposition → structured Instruction | Cannot advance step, issue blocked final-action directions or execute |
| Verification Agent | Evidence evaluation against declared criterion | Claim, fresh evidence, current versions → passed/mismatch/inconclusive/user_reported | Cannot treat user's Done as proof, mutate session directly or redefine success to fit result |
| Explanation/Debugger Agent | Why/how explanations and bounded technical diagnosis | User question, redacted relevant context → answer/hypotheses/manual diagnostic suggestion | Cannot rewrite whole project, silently change plan or override verifier |
| Voice Interface | Explicit clip transcription and command normalization | Consented bounded audio → editable transcript; reviewed transcript → command | Cannot infer consent from speech, keep listening, identify speaker or approve high risk |
| Safety and Privacy Guard | Deterministic risk/scope/media/consent/output checks | Request/role result + immutable policy/current grants → allow/confirm/block with reason | Cannot outsource final authorization to another model or hide capture |

Only Orchestrator writes GuideSession, TaskStep progression, Operation and event records. The Guard may synchronously veto a proposed mutation; local Windows gate may stop capture independently. Provider results are proposals until schema, authorization, epoch and safety checks pass.

## Coordination contract

Internal request envelope: `{request_id, operation_id, owner_scope, task_id, session_id, state_version, control_epoch, plan_version, instruction_version?, evidence_refs, intent, policy_version, deadline_at, budget, allowed_output_schema}`. `owner_scope` is a server-only authorization context, never raw JWT sent to provider. Result envelope: `{operation_id, status, evidence_refs, observations_or_output, uncertainty, missing_context, usage, error_code?}`. No role chooses recipients, URLs, tools or arbitrary other agents.

Sequence: Orchestrator checks current state/policy → dispatches Context/Vision if needed → checks result → dispatches Planner or Instruction/Verification → checks result → commits. Maximum one active media/model operation/session and 40 provider calls/session per 07. Retries bounded by 14. Cancel propagates to every role; result with old epoch is discarded. Build deterministic fixtures for each role before provider integration.

Example: Vision reports two similar Run icons. Instruction Agent must request disambiguation. Orchestrator asks for a crop and remains at the same step; it cannot ask a separate agent to click one and see what happens.

## Future Kurukul mapping

| Platform role | Future integration | Boundary preserved |
|---|---|---|
| Agent Zero | Authorize purpose-scoped cross-mode requests and coordinate high-level handoffs | User Mode Orchestrator still owns Guide sessions/consent; no basic dependency on Learner |
| Atlas | Supply teaching explanations as the Explanation role's provider | No duplicate session manager; user chooses deeper learning |
| Builder | Practical project/task expertise usable by Planner/Instruction through adapters | No new execution rights or direct file access |
| Detector | Opt-in aggregate progress/difficulty signals derived from task outcomes | No continuous desktop/focus surveillance; no raw screenshots |
| Scout | Suggest a structured learning path when user-approved difficulty patterns recur | No auto-enrollment or raw-media transfer |

Future handoff: Orchestrator proposes “You have asked for Python debugging help several times. Would you like to explore a Python learning path?” Show summary/skill tags to share, user confirms, Agent Zero checks purpose/mode/owner scope, Scout/Learner receives only approved minimum context. Refusal, unavailable platform or authorization denial keeps current Guide task fully usable. No agent copies institutional/user data across modes by default.

## Assumptions, dependencies, decisions and traceability

Assume roles may initially be ordinary functions sharing one provider adapter; do not create unnecessary microservices. Depends on 05/06/07/09/13 and ADR-013; D01 provider selection and future platform protocol are unresolved, with no MVP cross-mode network endpoint. SEC-07/08/09/10/16 apply. R18/R19/R20/R26 → F18/F19/F20/F26 → T18/T19/T20/T26 in [17](17-traceability-matrix.md).
