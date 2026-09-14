from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class Category(StrEnum):
    setup = "setup"
    run = "run"
    debug = "debug"
    understand = "understand"
    test = "test"
    git_github = "git_github"


class SessionState(StrEnum):
    task_created = "task_created"
    analyzing = "analyzing"
    plan_ready = "plan_ready"
    awaiting_user_confirmation = "awaiting_user_confirmation"
    awaiting_screen_permission = "awaiting_screen_permission"
    active = "active"
    capturing = "capturing"
    processing = "processing"
    instruction_ready = "instruction_ready"
    awaiting_user_action = "awaiting_user_action"
    verifying = "verifying"
    blocked = "blocked"
    paused = "paused"
    stopping = "stopping"
    completed = "completed"
    failed = "failed"
    expired = "expired"


class TaskCreate(Schema):
    goal: Annotated[str, Field(min_length=1, max_length=4000)]
    title: Annotated[str, Field(min_length=1, max_length=120)] = ""
    category: Category
    application_key: Annotated[str, Field(min_length=1, max_length=80)]


class Task(Schema):
    id: UUID
    title: str
    goal: str
    category: Category
    application_key: str
    status: Literal["open", "completed", "archived", "deleting"]
    current_session_id: UUID | None
    created_at: datetime
    updated_at: datetime


class Session(Schema):
    id: UUID
    task_id: UUID
    previous_session_id: UUID | None
    state: SessionState
    state_version: int
    control_epoch: int
    current_step_id: UUID | None
    confirmed_plan_version: int | None
    observation_mode: Literal["screenshot_only", "window"]
    observation_active: bool
    frames_observed: int
    controller_device_id: UUID | None
    outcome: Literal["achieved", "user_reported", "stopped", "failed", "expired"] | None
    checkpoint_state: SessionState | None
    expires_at: datetime
    last_user_activity_at: datetime
    created_at: datetime
    updated_at: datetime


class CreatedTask(Schema):
    task: Task
    session: Session


class UploadMetadata(Schema):
    session_id: UUID | None = None
    source: Literal["manual", "observation"]
    purpose: Literal["context", "verification", "error", "disagreement"]
    captured_at: AwareDatetime
    replaces_screenshot_id: UUID | None = None
    expected_version: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def check_version(self) -> "UploadMetadata":
        if self.session_id is not None and self.expected_version is None:
            raise ValueError("Session uploads require expected_version")
        return self


class Screenshot(Schema):
    id: UUID
    task_id: UUID
    session_id: UUID | None
    source: Literal["manual", "observation"]
    version: int
    status: Literal["accepted", "processing", "ready", "rejected", "deleting", "deleted", "expired"]
    width: int
    height: int
    content_type: str
    byte_size: int
    captured_at: datetime
    expires_at: datetime
    replaces_screenshot_id: UUID | None


class Uploaded(Schema):
    screenshot: Screenshot
    session: Session | None
    operation_id: UUID | None = None


class Step(Schema):
    id: UUID
    ordinal: Annotated[int, Field(ge=1, le=12)]
    title: str
    action: str
    expected_result: str
    success_criterion: str
    fallback: str
    explanation: str
    application_key: str
    risk: Literal["low", "medium", "high"]
    policy_disposition: Literal["allow", "confirm", "block"]
    evidence_kind: Literal["visual", "text", "self_report"]
    required: bool
    status: Literal[
        "pending",
        "instruction_ready",
        "awaiting_user_action",
        "user_claimed",
        "verified",
        "blocked",
        "skipped",
        "superseded",
    ]
    attempt_count: int
    verified_at: datetime | None


class Plan(Schema):
    id: UUID
    task_id: UUID
    session_id: UUID
    version: int
    status: Literal["draft", "confirmed", "superseded"]
    assumptions: list[str]
    policy_version: str
    confirmed_at: datetime | None
    steps: list[Step]
    created_at: datetime
    updated_at: datetime


class PlanRequest(Schema):
    session_id: UUID
    expected_version: Annotated[int, Field(ge=1)]


class ConfirmRequest(Schema):
    expected_version: Annotated[int, Field(ge=1)]
    plan_version: Annotated[int, Field(ge=1)]


class ConfirmedPlan(Schema):
    plan: Plan
    session: Session


class Instruction(Schema):
    id: UUID
    session_id: UUID
    step_id: UUID
    version: int
    status: Literal["ready", "superseded", "invalidated"]
    what: str
    where: str
    why: str | None
    confirmation_hint: str
    cannot_find_hint: str
    created_at: datetime


class CurrentInstruction(Schema):
    instruction: Instruction
    step: Step
    session: Session


class StartRequest(Schema):
    expected_version: Annotated[int, Field(ge=1)]
    observation_mode: Literal["screenshot_only"] = "screenshot_only"


class ClaimRequest(Schema):
    expected_version: Annotated[int, Field(ge=1)]
    statement: Annotated[str, Field(max_length=1000)] = ""


class SkipRequest(Schema):
    expected_version: Annotated[int, Field(ge=1)]
    reason: Literal["not_applicable", "already_done", "cannot_do"]


class Claimed(Schema):
    """A claim is the user's word. `verified` is always false here: only evidence
    can verify a step, and that is a separate record (ADR-010)."""

    claim_id: UUID
    step: Step
    session: Session
    verified: Literal[False] = False


class Skipped(Schema):
    step: Step
    session: Session
    next_operation_id: UUID | None = None


class CompletionRequest(Schema):
    """How a task ends. `achieved` is a claim about evidence, so the engine
    checks it; `user_reported` is the user's own account and is labelled as one
    everywhere it appears."""

    expected_version: Annotated[int, Field(ge=1)]
    outcome: Literal["achieved", "user_reported"]
    self_report: Annotated[str, Field(max_length=1000)] = ""


class Summary(Schema):
    """What happened, with checked work and reported work kept apart."""

    session_id: UUID
    outcome: Literal["achieved", "user_reported", "stopped", "failed", "expired"]
    verified_steps: list[UUID]
    unverified_steps: list[UUID]
    corrections: list[str]
    text: str
    next_action: str | None
    created_at: datetime


class Completed(Schema):
    session: Session
    summary: Summary


class ImportRequest(Schema):
    """A conversation the user already had, pasted in. Paste is the only
    transport: no extension, no connector, no third-party credential (ADR-018)."""

    text: Annotated[str, Field(min_length=20, max_length=32768)]
    source: Literal["chatgpt", "claude", "gemini", "other"] = "other"
    category: Category = Category.setup
    application_key: Annotated[str, Field(max_length=80)] = "unknown"


class ImportedConversation(Schema):
    id: UUID
    source: Literal["chatgpt", "claude", "gemini", "other"]
    redactions: int
    steps_extracted: int
    steps_blocked: int
    created_at: datetime


class ImportAccepted(Schema):
    """What an import creates: a task, a session, and work to produce a draft.

    Nothing is confirmed and nothing has started. The plan that arrives is
    reviewed and confirmed exactly like a generated one.
    """

    task: Task
    session: Session
    operation_id: UUID
    imported: ImportedConversation


class ReplanRequest(Schema):
    """Ask for a replacement roadmap for whatever is left.

    The reason recorded here is the user's; the planner is given what the session
    actually recorded — the stuck reason and any observed anomaly — rather than
    a claim typed by a client.
    """

    expected_version: Annotated[int, Field(ge=1)]
    reason: Literal["stuck", "anomaly", "user"] = "user"


class VerifyRequest(Schema):
    """Doc 07's verification route needs evidence or an explicit self-report.
    Only the self-report arm exists today: objective checking arrives with the
    evidence path, so `evidence_ids` is accepted and refused rather than quietly
    ignored."""

    expected_version: Annotated[int, Field(ge=1)]
    claim_id: UUID
    self_report: Annotated[str, Field(max_length=1000)] = ""
    evidence_ids: Annotated[list[UUID], Field(max_length=3)] = []


class Verification(Schema):
    id: UUID
    session_id: UUID
    step_id: UUID
    claim_id: UUID | None
    status: Literal["pending", "passed", "mismatch", "inconclusive", "user_reported", "canceled"]
    verifier_kind: Literal["visual", "text", "self_report"]
    reason: str
    observed_confidence: float | None
    evidence_available: bool
    instruction_version: int
    created_at: datetime


class SelfReported(Schema):
    """What a self-report earns. `verified` stays false in every field that
    could be mistaken for a pass: the step is still `user_claimed` and the
    session can only ever end `user_reported` on this evidence (doc 05)."""

    verification: Verification
    step: Step
    session: Session
    verified: Literal[False] = False
    next_operation_id: UUID | None = None


class Event(Schema):
    """One entry in the session's ordered, content-free history."""

    sequence: int
    state_version: int
    control_epoch: int
    type: str
    payload: dict
    created_at: datetime


class EventPage(Schema):
    items: list[Event]
    # Pass back as `after` to resume exactly here. Stable across reconnects.
    next_after: int


class ObservationConsent(Schema):
    """Explicit, separate consent for continuous watching. Accepting a screenshot
    upload does not imply this, and the version pins what was actually agreed to."""

    expected_version: Annotated[int, Field(ge=1)]
    consent_version: Annotated[str, Field(min_length=1, max_length=40)]
    accepted: Literal[True]


class ObservationState(Schema):
    active: bool
    frames_observed: int
    observation_calls_remaining: int
    consent_version: str
    session: Session


class ObserveRequest(Schema):
    """One admitted frame. No idempotency key: a tick is not a command, and
    replaying one would be meaningless. Rate limits protect it instead."""

    expected_version: Annotated[int, Field(ge=1)]
    image_base64: Annotated[str, Field(min_length=1, max_length=5_592_408)]
    admitted_at: AwareDatetime


class ObservationTick(Schema):
    """What the tick earned. `advance` is the only decision that moves anything."""

    decision: Literal["advance", "ask", "wait"]
    confidence: Annotated[float, Field(ge=0, le=1)]
    ui_changed: bool
    anomaly: Literal[
        "none", "different_os", "different_app", "outdated_ui", "error_dialog", "unreadable"
    ]
    note: str
    frames_observed: int
    observation_calls_remaining: int
    session: Session


class AnalyzeRequest(Schema):
    session_id: UUID
    expected_version: Annotated[int, Field(ge=1)]
    screenshot_ids: Annotated[list[UUID], Field(min_length=1, max_length=3)]
    question: Annotated[str, Field(min_length=1, max_length=4000)]


class BBox(Schema):
    x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    width: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]

    @model_validator(mode="after")
    def inside(self) -> "BBox":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Box must stay inside the image")
        return self


class Observation(Schema):
    label: Annotated[str, Field(min_length=1, max_length=120)]
    bbox: BBox | None
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Analysis(Schema):
    id: UUID
    screenshot_ids: list[UUID]
    observations: list[Observation]
    explanation: Annotated[str, Field(max_length=4000)]
    needs_context: bool
    context_request: Annotated[str, Field(max_length=500)] | None


class ErrorBody(Schema):
    code: str
    message: str
    retryable: bool


class ErrorDetails(Schema):
    current_version: int | None = None
    retry_after_seconds: int | None = None


class TransportError(ErrorBody):
    details: ErrorDetails | None = None


class ErrorEnvelope(Schema):
    error: TransportError
    request_id: UUID


class Operation(Schema):
    id: UUID
    kind: Literal["analyze", "plan", "instruct"]
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    session_id: UUID | None
    result: Analysis | None
    # What the operation produced, when the result is fetched by its own route.
    # A plan operation carries the plan id here and leaves `result` empty.
    result_id: UUID | None = None
    error: ErrorBody | None
    created_at: datetime
    updated_at: datetime


class Pending(Schema):
    operation_id: UUID
    session: Session | None
    poll_after_ms: int = 2000


class DeletionReceipt(Schema):
    id: UUID
    scope: Literal["screenshot", "session", "task", "account"]
    status: Literal["queued", "purging", "purged", "failed"]
    requested_at: datetime
    online_purge_due_at: datetime
    backup_expiry_due_at: datetime | None
    completed_at: datetime | None


class PauseRequest(Schema):
    expected_version: Annotated[int, Field(ge=1)] | None = None
    reason: Literal["user", "network", "auth", "lock", "suspend", "controller_lost"]


class StopRequest(Schema):
    expected_version: Annotated[int, Field(ge=1)] | None = None
    reason: Literal["user", "close", "sign_out", "emergency"]


class ResumeRequest(Schema):
    """Doc 07's resume shape. `checkpoint_reviewed` is not a formality: doc 05
    requires the user to have seen where the guide is before it starts pointing
    again, and a paused or blocked session is usually paused or blocked because
    something was wrong."""

    expected_version: Annotated[int, Field(ge=1)] | None = None
    mode: Literal["screenshot_only", "window"] = "screenshot_only"
    checkpoint_reviewed: bool = False
    device_id: UUID | None = None


class Resumed(Schema):
    session: Session
    #: Set when the guide needs a fresh instruction before anything is waiting on
    #: the user: a resume after `incorrect_guidance` withdrew the old one.
    next_operation_id: UUID | None = None


class RetryRequest(Schema):
    """Ask for this step to be explained again. Not a verification and not a
    skip: nothing about the step's status changes, only the words."""

    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(max_length=1000)] = ""


class ContextTickRequest(Schema):
    """One admitted frame, for the context observer. Same shape as `/observe`:
    the browser has already discarded almost everything (ADR-016 tiers 0 and 1)."""

    expected_version: Annotated[int, Field(ge=1)]
    image_base64: Annotated[str, Field(min_length=1, max_length=6_000_000)]
    admitted_at: AwareDatetime


class SeenControl(Schema):
    label: str
    box: tuple[float, float, float, float]
    kind: str


class SkipOffer(Schema):
    """What a forward skip would settle, named before it happens."""

    step_ids: list[UUID] = []
    titles: list[str] = []


class ContextTick(Schema):
    """What the guide now believes, and whether it changed anything.

    `instruction_pending` is the field that matters for cost: false means the
    screen is the same screen as far as guidance is concerned, and no reasoning
    call was made.
    """

    stage: Literal[
        "before_start", "in_progress", "step_satisfied", "later_step_satisfied",
        "off_track", "blocked_dialog", "unreadable",
    ]
    application: str
    application_matches_expected: bool
    screen: str
    dialog: str | None = None
    error_text: str | None = None
    controls: list[SeenControl] = []
    confidence: float
    digest: str
    changed: bool
    note: str = ""
    observation_calls_remaining: int
    session: Session
    #: What the guide decided to do about this screen. `none` is the common case
    #: and the cheap one.
    action: Literal[
        "none", "check", "redirect", "wrong_application", "dialog", "offer_skip", "unreadable"
    ] = "none"
    #: Copy for the island, in the user's language. Empty when nothing is wrong.
    message: str = ""
    #: Present only with `offer_skip`. Nothing is settled until the user accepts.
    offer: SkipOffer | None = None


class SkipForwardRequest(Schema):
    """Accept the forward skip the guide offered.

    The step ids are echoed back so a stale offer cannot settle steps the user
    never saw named.
    """

    expected_version: Annotated[int, Field(ge=1)]
    step_ids: Annotated[list[UUID], Field(min_length=1, max_length=11)]


class SkippedForward(Schema):
    steps: list[Step]
    session: Session
    next_operation_id: UUID | None = None


class FeedbackRequest(Schema):
    """Doc 07's feedback shape. `incorrect_guidance` is the expensive one: doc 05
    has it invalidate the pointer, revoke observation and block the session, so
    it names the step it is about."""

    expected_version: Annotated[int, Field(ge=1)] | None = None
    kind: Literal["incorrect_guidance", "helpful", "unhelpful", "privacy_concern"]
    step_id: UUID | None = None
    instruction_id: UUID | None = None
    text: Annotated[str, Field(max_length=2000)] = ""


class FeedbackRecorded(Schema):
    feedback_id: UUID
    session: Session
    step: Step | None = None
    #: True when the user contradicted a pass the observer reached on its own.
    #: The step is `pending` again and nothing claims it was verified.
    verification_withdrawn: bool = False


class SessionItem(Schema):
    session: Session
    task_title: str


class SessionList(Schema):
    items: list[SessionItem]
    next_cursor: str | None


class Envelope[T](Schema):
    data: T
    request_id: UUID
