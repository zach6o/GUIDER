"""Provider-facing role contracts and capability descriptors.

Adapters implement bounded roles and return validated structures, never free text
([ADR-017](../../../../docs/user-mode-guide/adr/017-provider-role-abstraction.md)).
Selection is by role and capability; a provider name must not be compared outside
this package.

The `analyze`, `guide`, `plan`, `instruct` and `observe` roles below exist today. The
remaining roles in `Role` are declared so the registry and descriptors are ready
for them; their Protocols land with the phase that implements them, because a
Protocol no adapter satisfies is fiction.
"""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import Field, SecretStr

from app.errors import GuideError
from app.schemas import Analysis, Schema

MODEL = Literal["gpt-4.1-mini", "gpt-4.1"]
MAX_IMAGE = 4 * 1024 * 1024

Role = Literal["analyze", "guide", "observe", "plan", "instruct", "verify", "import"]
StructuredOutput = Literal["json_schema", "tool", "native", "prompt", "none"]
CostTier = Literal["cheap", "standard", "capable"]


class CheckInput(Schema):
    goal: str = Field(min_length=1, max_length=4000)
    question: str = Field(max_length=1000)
    previous_step: str = Field(max_length=1000)
    image_base64: str = Field(min_length=1, max_length=5_592_408)
    reviewed: Literal[True]


class Guidance(Schema):
    observation: str = Field(min_length=1, max_length=1600)
    next_step: str = Field(max_length=1000)
    where: str = Field(max_length=500)
    check_for: str = Field(max_length=500)
    question: str = Field(max_length=500)
    disposition: Literal["guide", "needs_context", "blocked"]


class PlanContext(Schema):
    """Everything a planner may see. No screen content and no account data.

    Replanning adds only what the planner needs to avoid repeating work: the
    titles of steps already behind the guide, why a new plan was asked for, and
    the anomaly an observer reported, if any. Titles are the planner's own
    earlier words, not anything read from the user's screen.
    """

    goal: str = Field(min_length=1, max_length=4000)
    category: str = Field(max_length=30)
    application_key: str = Field(max_length=80)
    reason: Literal["initial", "stuck", "anomaly", "user"] = "initial"
    completed: list[Annotated[str, Field(max_length=120)]] = Field(max_length=12, default=[])
    anomaly: Literal[
        "none", "different_os", "different_app", "outdated_ui", "error_dialog", "unreadable"
    ] = "none"


class ProposedStep(Schema):
    title: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=1000)
    expected_result: str = Field(max_length=500)
    success_criterion: str = Field(min_length=1, max_length=500)
    fallback: str = Field(max_length=500)
    explanation: str = Field(max_length=1000)
    application_key: str = Field(min_length=1, max_length=80)
    risk: Literal["low", "medium", "high"] = "low"
    evidence_kind: Literal["visual", "text", "self_report"] = "visual"
    required: bool = True


class ProposedPlan(Schema):
    """A proposal, never a confirmed plan: 1-12 steps, per ADR-010."""

    assumptions: list[Annotated[str, Field(max_length=300)]] = Field(max_length=8, default=[])
    steps: list[ProposedStep] = Field(min_length=1, max_length=12)


class InstructionContext(Schema):
    """What an instruction writer may see: the confirmed step and the goal it
    serves. No account data, and no screen content until observation exists."""

    goal: str = Field(min_length=1, max_length=4000)
    application_key: str = Field(max_length=80)
    title: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=1000)
    expected_result: str = Field(max_length=500)
    fallback: str = Field(max_length=500)
    explanation: str = Field(max_length=1000)
    ordinal: int = Field(ge=1, le=12)
    total_steps: int = Field(ge=1, le=12)


class ProposedInstruction(Schema):
    """One action the user performs. The writer cannot advance the step."""

    what: str = Field(min_length=1, max_length=1000)
    where: str = Field(max_length=300)
    why: str = Field(max_length=500)
    confirmation_hint: str = Field(max_length=300)
    cannot_find_hint: str = Field(max_length=300)


class ObserveContext(Schema):
    """What the observer is asked. It receives the step's testable condition, not
    the prose shown to the user, and no history."""

    success_criterion: str = Field(min_length=1, max_length=500)
    expected_result: str = Field(max_length=500)
    application_key: str = Field(max_length=80)


class ObserveResult(Schema):
    """Evidence about the current screen, and nothing else.

    There is deliberately no next_step, where, or any other directive field: the
    observer answers questions, it does not write guidance (ADR-016). A cheap
    model answering a constrained question is what keeps tier 2 affordable.
    """

    step_complete: bool
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    app_visible: str = Field(max_length=80)
    ui_changed: bool
    anomaly: Literal[
        "none", "different_os", "different_app", "outdated_ui", "error_dialog", "unreadable"
    ] = "none"
    note: str = Field(max_length=200)


@dataclass(frozen=True)
class CapabilityDescriptor:
    """What an adapter can do. The registry selects on this, never on `id`."""

    id: str
    display_name: str
    roles: frozenset[Role]
    vision: bool
    structured_output: StructuredOutput
    max_image_px: int
    cost_tier: CostTier
    byok_only: bool
    local: bool

    def supports(self, role: Role) -> bool:
        return role in self.roles


class AnalysisProvider(Protocol):
    """Role `analyze`: owned account evidence to a validated explanation."""

    async def analyze(self, images: list[tuple[str, bytes]]) -> Analysis: ...


class Planner(Protocol):
    """Role `plan`: a goal to a bounded roadmap. Cannot confirm its own plan or
    widen the task or application scope (see doc 12, agent responsibilities)."""

    async def plan(self, ctx: PlanContext) -> ProposedPlan: ...


class InstructionWriter(Protocol):
    """Role `instruct`: one confirmed step to one validated instruction. Cannot
    advance the step or issue a blocked final action (doc 12)."""

    async def instruct(self, ctx: InstructionContext) -> ProposedInstruction: ...


class VisionObserver(Protocol):
    """Role `observe`: one admitted frame to one verdict. Cannot advance a step,
    write an instruction, or see anything but the current frame."""

    async def observe(self, ctx: ObserveContext, image: bytes) -> ObserveResult: ...


class LiveGuidanceProvider(Protocol):
    """Role `guide`: one reviewed frame to one validated next step, under a
    caller-supplied credential that this process never persists."""

    async def validate(self, key: SecretStr, model: str) -> None: ...

    async def analyze(
        self, key: SecretStr, model: str, body: CheckInput, image: bytes
    ) -> Guidance: ...


def provider_error(status: int) -> GuideError:
    if status in {401, 403}:
        return GuideError(
            401, "openai_key_rejected", "OpenAI rejected this key or its permissions."
        )
    if status == 429:
        return GuideError(
            429,
            "openai_limit",
            "OpenAI's usage limit was reached. Check your API billing and limits.",
        )
    if status == 404:
        return GuideError(422, "model_unavailable", "This model is not available for your API key.")
    return GuideError(
        503,
        "openai_unavailable",
        "OpenAI could not complete this request. Try again.",
        retryable=True,
    )
