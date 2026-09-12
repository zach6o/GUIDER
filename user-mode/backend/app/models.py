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
