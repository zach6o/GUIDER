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

Role = Literal[
    "analyze", "guide", "observe", "observe_context", "plan", "instruct", "verify", "import"
]
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


STAGES = (
    "before_start",
    "in_progress",
    "step_satisfied",
    "later_step_satisfied",
    "off_track",
    "blocked_dialog",
    "unreadable",
)


class VisibleControl(Schema):
    """One control the observer says it can see, in normalised frame coordinates.

    `0..1` against the frame, never pixels: the same payload then places a mark on
    a mirrored preview today and on a native desktop overlay later, across DPI,
    zoom and monitor changes ([ADR-020](../../../docs/user-mode-guide/adr/020-overlay-surfaces.md)).
    """

    label: str = Field(min_length=1, max_length=80)
    box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    kind: Literal["button", "field", "menu", "tab", "link", "dialog", "other"] = "other"


class ContextRequest(Schema):
    """What the context observer is asked. It sees the current step's testable
    condition and the application it should be looking at — no history, no goal,
    no account data."""

    success_criterion: str = Field(min_length=1, max_length=500)
    expected_result: str = Field(max_length=500)
    application_key: str = Field(max_length=80)
    step_title: str = Field(max_length=120)
    later_titles: list[Annotated[str, Field(max_length=120)]] = Field(max_length=11, default=[])


class ScreenContext(Schema):
    """A belief about the shared window. Never a verification.

    Nothing here can mark a step verified: `stage` is what the guide reads, and a
    step advances only through the verification path with its own bands
    ([ADR-019](../../../docs/user-mode-guide/adr/019-context-engine.md)).
    """

    application: str = Field(max_length=80, default="")
    application_matches_expected: bool = True
    screen: str = Field(max_length=120, default="")
    stage: Literal[STAGES] = "in_progress"  # type: ignore[valid-type]
    controls: list[VisibleControl] = Field(max_length=12, default=[])
    dialog: str = Field(max_length=200, default="")
    error_text: str = Field(max_length=200, default="")
    #: Which of `later_titles` the screen already satisfies, by index. Only read
    #: when `stage` is `later_step_satisfied`.
    satisfied_later_index: int | None = None
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False, default=0.0)
    note: str = Field(max_length=200, default="")


class ImportContext(Schema):
    """A transcript the user pasted, and where they say it came from.

    Untrusted in full. An importer reads it the way it would read text off a
    screenshot: as evidence about what the user wants, never as instructions
    (ADR-018, SEC-09).
    """

    transcript: str = Field(min_length=1, max_length=32768)
    source: Literal["chatgpt", "claude", "gemini", "other"] = "other"


class ImportedTask(Schema):
    """What an importer may propose: a goal and a candidate roadmap.

    There is deliberately nothing here that could start anything. No confirmed
    plan, no session, no provider or policy field — an import ends in a draft the
    user confirms, like every other plan (ADR-010, ADR-018).
    """

    goal: str = Field(min_length=1, max_length=4000)
    application_key: str = Field(max_length=80, default="unknown")
    plan: ProposedPlan


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
    # Model names live with the adapter that understands them, so nothing
    # outside this package has to know one provider's names from another's.
    models: tuple[str, ...] = ()
    default_model: str = ""

    def supports(self, role: Role) -> bool:
        return role in self.roles

    def model_or_default(self, model: str) -> str:
        """The model to use, or a refusal that names neither provider nor model."""
        chosen = model or self.default_model
        if not chosen or len(chosen) > 120:
            raise GuideError(
                422, "model_unavailable", "Enter a model name of at most 120 characters."
            )
        if self.models and chosen not in self.models and not self.local:
            raise GuideError(
                422, "model_unavailable", "That model is not available for this connection."
            )
        return chosen


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


class ContextObserver(Protocol):
    """Role `observe_context`: one frame to a belief about what is on screen."""

    async def observe_context(self, ctx: ContextRequest, image: bytes) -> ScreenContext: ...


class VisionObserver(Protocol):
    """Role `observe`: one admitted frame to one verdict. Cannot advance a step,
    write an instruction, or see anything but the current frame."""

    async def observe(self, ctx: ObserveContext, image: bytes) -> ObserveResult: ...


class ConversationImporter(Protocol):
    """Role `import`: a pasted transcript to a proposed goal and roadmap. Cannot
    confirm a plan, start a session or take anything in the text as an
    instruction (ADR-018)."""

    async def import_conversation(self, ctx: ImportContext) -> ImportedTask: ...


class LiveGuidanceProvider(Protocol):
    """Role `guide`: one reviewed frame to one validated next step, under a
    caller-supplied credential that this process never persists."""

    async def validate(self, key: SecretStr, model: str) -> None: ...

    async def analyze(
        self, key: SecretStr, model: str, body: CheckInput, image: bytes
    ) -> Guidance: ...


def provider_error(status: int, provider: str = "OpenAI") -> GuideError:
    """One refusal shape for every adapter. The name is the provider's own, so a
    message can say who refused without any caller branching on which one."""
    if status in {401, 403}:
        return GuideError(
            401, "openai_key_rejected", f"{provider} rejected this key or its permissions."
        )
    if status == 429:
        return GuideError(
            429,
            "openai_limit",
            f"{provider}'s usage limit was reached. Check your API billing and limits.",
        )
    if status == 404:
        return GuideError(422, "model_unavailable", "This model is not available for your API key.")
    # The codes keep their original spelling: the web client already branches on
    # `openai_key_rejected`, and renaming a wire code is a contract change.
    return GuideError(
        503,
        "openai_unavailable",
        f"{provider} could not complete this request. Try again.",
        retryable=True,
    )
