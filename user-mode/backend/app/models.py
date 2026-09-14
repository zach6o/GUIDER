from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime, TypeDecorator

# Portable development enums from 08-data-model.md, enforced as CHECK constraints
# until the PostgreSQL migration introduces native types.
PLAN_STATUSES = ("draft", "confirmed", "superseded")
STEP_STATUSES = (
    "pending",
    "instruction_ready",
    "awaiting_user_action",
    "user_claimed",
    "verified",
    "blocked",
    "skipped",
    "superseded",
)
INSTRUCTION_STATUSES = ("ready", "superseded", "invalidated")
CLAIM_STATUSES = ("user_claimed", "superseded")
VERIFICATION_STATUSES = (
    "pending",
    "passed",
    "mismatch",
    "inconclusive",
    "user_reported",
    "canceled",
)
RISKS = ("low", "medium", "high")
DISPOSITIONS = ("allow", "confirm", "block")
EVIDENCE_KINDS = ("visual", "text", "self_report")


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(default="active")
    locale: Mapped[str] = mapped_column(default="en")
    privacy_notice_version: Mapped[str] = mapped_column(default="development-1")
    analytics_opt_in: Mapped[bool] = mapped_column(default=False)
    auth_revoked_before: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Owned:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now, onupdate=now)


class GuideTask(Owned, Base):
    __tablename__ = "guide_tasks"
    __table_args__ = (UniqueConstraint("owner_id", "id"),)
    title: Mapped[str] = mapped_column(String(120))
    goal: Mapped[str] = mapped_column(String(4000))
    category: Mapped[str] = mapped_column(String(30))
    application_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(default="open")
    current_session_id: Mapped[str | None] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class GuideSession(Owned, Base):
    __tablename__ = "guide_sessions"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "task_id", "id"),
        ForeignKeyConstraint(["owner_id", "task_id"], ["guide_tasks.owner_id", "guide_tasks.id"]),
    )
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    previous_session_id: Mapped[str | None] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(default="task_created")
    state_version: Mapped[int] = mapped_column(BigInteger, default=1)
    control_epoch: Mapped[int] = mapped_column(BigInteger, default=1)
    checkpoint_state: Mapped[str | None]
    current_step_id: Mapped[str | None]
    confirmed_plan_version: Mapped[int | None]
    controller_device_id: Mapped[str | None]
    observation_mode: Mapped[str] = mapped_column(default="screenshot_only")
    outcome: Mapped[str | None]
    last_user_activity_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    # Observation accounting (ADR-016). Frames are never stored; only these counts.
    observation_active: Mapped[bool] = mapped_column(default=False)
    observation_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    frames_observed: Mapped[int] = mapped_column(default=0)
    observation_calls: Mapped[int] = mapped_column(default=0)
    reasoning_calls: Mapped[int] = mapped_column(default=0)
    stuck_since: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class TaskPlan(Owned, Base):
    """An immutable proposed roadmap. A new version supersedes the old one;
    only an explicitly confirmed version may start guidance (ADR-010)."""

    __tablename__ = "task_plans"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "session_id", "version"),
        ForeignKeyConstraint(["owner_id", "task_id"], ["guide_tasks.owner_id", "guide_tasks.id"]),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        CheckConstraint(f"status IN {PLAN_STATUSES}", name="task_plans_status"),
        CheckConstraint("version >= 1", name="task_plans_version"),
    )
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="draft")
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    confirmed_by: Mapped[str | None] = mapped_column(String(36))
    policy_version: Mapped[str] = mapped_column(default="development-1")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class TaskStep(Owned, Base):
    """One step definition owned by one plan version. The definition is immutable;
    only the runtime columns (status, attempt_count, verified_at) change."""

    __tablename__ = "task_steps"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "plan_id", "ordinal"),
        # Steps cannot outlive their plan version: removing a plan removes them.
        ForeignKeyConstraint(
            ["owner_id", "plan_id"],
            ["task_plans.owner_id", "task_plans.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        CheckConstraint("ordinal >= 1 AND ordinal <= 12", name="task_steps_ordinal"),
        CheckConstraint(f"status IN {STEP_STATUSES}", name="task_steps_status"),
        CheckConstraint(f"risk IN {RISKS}", name="task_steps_risk"),
        CheckConstraint(f"policy_disposition IN {DISPOSITIONS}", name="task_steps_disposition"),
        CheckConstraint(f"evidence_kind IN {EVIDENCE_KINDS}", name="task_steps_evidence"),
    )
    plan_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    previous_step_id: Mapped[str | None] = mapped_column(String(36))
    ordinal: Mapped[int]
    title: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(1000))
    # Shown to the user; `success_criterion` is the condition the verifier tests.
    expected_result: Mapped[str] = mapped_column(String(500), default="")
    success_criterion: Mapped[str] = mapped_column(String(500))
    fallback: Mapped[str] = mapped_column(String(500), default="")
    explanation: Mapped[str] = mapped_column(String(1000), default="")
    application_key: Mapped[str] = mapped_column(String(80))
    risk: Mapped[str] = mapped_column(default="low")
    policy_disposition: Mapped[str] = mapped_column(default="allow")
    evidence_kind: Mapped[str] = mapped_column(default="visual")
    required: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(default="pending")
    attempt_count: Mapped[int] = mapped_column(default=0)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Instruction(Owned, Base):
    """One action for one step. Only one instruction per session is current."""

    __tablename__ = "instructions"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "step_id", "version"),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        ForeignKeyConstraint(
            ["owner_id", "step_id"],
            ["task_steps.owner_id", "task_steps.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN {INSTRUCTION_STATUSES}", name="instructions_status"),
        CheckConstraint("version >= 1", name="instructions_version"),
    )
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    step_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="ready")
    what: Mapped[str] = mapped_column(String(1000))
    # Quoted by SQLAlchemy: `where` is reserved in SQL.
    where: Mapped[str] = mapped_column(String(300), default="")
    why: Mapped[str | None] = mapped_column(String(500))
    confirmation_hint: Mapped[str] = mapped_column(String(300), default="")
    cannot_find_hint: Mapped[str] = mapped_column(String(300), default="")
    pointer: Mapped[dict | None] = mapped_column(JSON)
    control_epoch: Mapped[int] = mapped_column(BigInteger, default=1)
    evidence_available: Mapped[bool] = mapped_column(default=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class CompletionClaim(Owned, Base):
    """The user's word that a step is done. Not a verification result, and never
    treated as one (ADR-010)."""

    __tablename__ = "completion_claims"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        ForeignKeyConstraint(
            ["owner_id", "step_id"],
            ["task_steps.owner_id", "task_steps.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN {CLAIM_STATUSES}", name="completion_claims_status"),
    )
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    step_id: Mapped[str] = mapped_column(String(36), index=True)
    statement: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(default="user_claimed")
    instruction_version: Mapped[int]
    claimed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class VerificationResult(Owned, Base):
    """Evidence, as distinct from a claim. A step is `verified` only when one of
    these says so; the user's word produces a CompletionClaim instead (ADR-010)."""

    __tablename__ = "verification_results"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        ForeignKeyConstraint(
            ["owner_id", "step_id"],
            ["task_steps.owner_id", "task_steps.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN {VERIFICATION_STATUSES}", name="verification_results_status"),
        CheckConstraint(f"verifier_kind IN {EVIDENCE_KINDS}", name="verification_results_kind"),
    )
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    step_id: Mapped[str] = mapped_column(String(36), index=True)
    claim_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(default="pending")
    verifier_kind: Mapped[str] = mapped_column(default="visual")
    reason: Mapped[str] = mapped_column(String(1000), default="")
    observed_confidence: Mapped[float | None]
    evidence_available: Mapped[bool] = mapped_column(default=True)
    instruction_version: Mapped[int]
    control_epoch: Mapped[int] = mapped_column(BigInteger, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


OUTCOMES = ("achieved", "user_reported", "stopped", "failed", "expired")


class SessionSummary(Owned, Base):
    """What happened, written down once when a session ends.

    The distinction the whole record exists for: `verified_steps` are steps
    something checked, and `unverified_steps` are steps the user said were done.
    A summary that blurred the two would undo what ADR-010 and the verification
    model are for, so they are separate columns rather than one list with a flag.
    """

    __tablename__ = "session_summaries"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        # One session, one summary: it describes an ending, and there is one.
        UniqueConstraint("owner_id", "session_id"),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        CheckConstraint(f"outcome IN {OUTCOMES}", name="session_summaries_outcome"),
    )
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    outcome: Mapped[str]
    verified_steps: Mapped[list] = mapped_column(JSON, default=list)
    unverified_steps: Mapped[list] = mapped_column(JSON, default=list)
    corrections: Mapped[list] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(String(4000), default="")
    next_action: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(default="ready")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


FEEDBACK_KINDS = ("incorrect_guidance", "helpful", "unhelpful", "privacy_concern")
FEEDBACK_STATUSES = ("received", "reviewed", "resolved")


class UserFeedback(Owned, Base):
    """What the user thought of a step, and — for `incorrect_guidance` — the only
    ground truth Guider ever gets about a verdict it reached on its own.

    Doc 05 makes this kind expensive on purpose: it invalidates the pointer,
    revokes observation and blocks the session. That cost is why the row is worth
    trusting when [D05](../../../docs/user-mode-guide/README.md) calibration reads
    it back. No frame is kept, so this and the tick event are all the evidence
    there is that an advance was wrong.
    """

    __tablename__ = "user_feedback"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        CheckConstraint(f"kind IN {FEEDBACK_KINDS}", name="user_feedback_kind"),
        CheckConstraint(f"status IN {FEEDBACK_STATUSES}", name="user_feedback_status"),
    )
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    step_id: Mapped[str | None] = mapped_column(String(36), index=True)
    instruction_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(index=True)
    text: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(default="received")
    # What the session believed when the user disagreed. Kept on the row because
    # the verification it contradicts may be purged before the feedback is read.
    verification_id: Mapped[str | None] = mapped_column(String(36))
    observed_confidence: Mapped[float | None]
    control_epoch: Mapped[int] = mapped_column(BigInteger, default=1)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


IMPORT_SOURCES = ("chatgpt", "claude", "gemini", "other")


class ImportedConversation(Owned, Base):
    """One pasted transcript, kept for provenance and nothing else.

    Untrusted data in exactly the sense of SEC-09: nothing in `transcript` is an
    instruction, whatever it claims about itself. It is stored redacted, once,
    under retention class H, and is erased with the task it belongs to
    ([ADR-018](../../../docs/user-mode-guide/adr/018-imported-conversation-context.md)).
    """

    __tablename__ = "imported_conversations"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        # One import per session: the draft it produced is the session's plan.
        UniqueConstraint("owner_id", "session_id"),
        ForeignKeyConstraint(
            ["owner_id", "task_id"],
            ["guide_tasks.owner_id", "guide_tasks.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        CheckConstraint(f"source IN {IMPORT_SOURCES}", name="imported_conversations_source"),
    )
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(default="other")
    # Redacted at import. Recognized secrets are dropped rather than stored.
    transcript: Mapped[str] = mapped_column(String(32768))
    redactions: Mapped[int] = mapped_column(default=0)
    extracted_goal: Mapped[str] = mapped_column(String(4000), default="")
    steps_extracted: Mapped[int] = mapped_column(default=0)
    steps_blocked: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class ScreenshotRow(Owned, Base):
    __tablename__ = "screenshots"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(["owner_id", "task_id"], ["guide_tasks.owner_id", "guide_tasks.id"]),
        ForeignKeyConstraint(
            ["owner_id", "task_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.task_id", "guide_sessions.id"],
        ),
    )
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(default="manual")
    purpose: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="ready")
    content_type: Mapped[str] = mapped_column(default="image/png")
    byte_size: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int]
    height: Mapped[int]
    object_key: Mapped[str | None]
    content_hash: Mapped[str | None]
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    replaces_screenshot_id: Mapped[str | None]
    redaction_version: Mapped[str] = mapped_column(default="client-opaque-v1")
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AnalysisRow(Owned, Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "task_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.task_id", "guide_sessions.id"],
        ),
    )
    task_id: Mapped[str]
    session_id: Mapped[str]
    status: Mapped[str] = mapped_column(default="ready")
    observations: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(String(4000))
    needs_context: Mapped[bool]
    context_request: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class OperationRow(Owned, Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "task_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.task_id", "guide_sessions.id"],
        ),
    )
    task_id: Mapped[str]
    session_id: Mapped[str]
    kind: Mapped[str] = mapped_column(default="analyze")
    status: Mapped[str] = mapped_column(default="queued", index=True)
    expected_state_version: Mapped[int]
    control_epoch: Mapped[int]
    request_digest: Mapped[str]
    result_ref: Mapped[str | None]
    error_code: Mapped[str | None]
    attempt_count: Mapped[int] = mapped_column(default=0)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class OperationEvidence(Base):
    __tablename__ = "operation_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "operation_id"],
            ["operations.owner_id", "operations.id"],
        ),
        ForeignKeyConstraint(
            ["owner_id", "screenshot_id"],
            ["screenshots.owner_id", "screenshots.id"],
        ),
    )
    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    screenshot_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int]


class IdempotencyRecord(Owned, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("owner_id", "method", "route", "key"),)
    method: Mapped[str]
    route: Mapped[str]
    key: Mapped[str]
    request_digest: Mapped[str]
    status_code: Mapped[int]
    response_ref: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="committed")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class DeletionJob(Owned, Base):
    __tablename__ = "deletion_jobs"
    __table_args__ = (UniqueConstraint("owner_id", "resource_id"),)
    scope: Mapped[str] = mapped_column(default="screenshot")
    resource_id: Mapped[str]
    status: Mapped[str] = mapped_column(default="purged")
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    online_purge_due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    backup_expiry_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class GuidanceEvent(Owned, Base):
    __tablename__ = "guidance_events"
    __table_args__ = (UniqueConstraint("session_id", "sequence"),)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int]
    state_version: Mapped[int]
    control_epoch: Mapped[int]
    type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    request_id: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
