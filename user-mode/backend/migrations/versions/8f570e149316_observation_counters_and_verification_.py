"""observation_counters_and_verification_results"""

import sqlalchemy as sa
from alembic import op

revision = "8f570e149316"
down_revision = "174286596589"
branch_labels = None
depends_on = None

# Counters only. Observation frames are never stored, so there is no media table
# here and none is coming (ADR-016).
COUNTERS = (
    ("observation_active", sa.Boolean(), sa.false()),
    ("frames_observed", sa.Integer(), sa.text("0")),
    ("observation_calls", sa.Integer(), sa.text("0")),
    ("reasoning_calls", sa.Integer(), sa.text("0")),
)
TIMESTAMPS = ("observation_started_at", "stuck_since")


def upgrade():
    for name, kind, default in COUNTERS:
        op.add_column(
            "guide_sessions",
            sa.Column(name, kind, nullable=False, server_default=default),
        )
    for name in TIMESTAMPS:
        op.add_column(
            "guide_sessions", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "verification_results",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("verifier_kind", sa.String(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("observed_confidence", sa.Float(), nullable=True),
        sa.Column("evidence_available", sa.Boolean(), nullable=False),
        sa.Column("instruction_version", sa.Integer(), nullable=False),
        sa.Column("control_epoch", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'passed', 'mismatch', 'inconclusive', "
            "'user_reported', 'canceled')",
            name="verification_results_status",
        ),
        sa.CheckConstraint(
            "verifier_kind IN ('visual', 'text', 'self_report')",
            name="verification_results_kind",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "step_id"],
            ["task_steps.owner_id", "task_steps.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
    )
    for column in ("expires_at", "owner_id", "session_id", "step_id"):
        op.create_index(
            op.f(f"ix_verification_results_{column}"),
            "verification_results",
            [column],
            unique=False,
        )


def downgrade():
    for column in ("step_id", "session_id", "owner_id", "expires_at"):
        op.drop_index(
            op.f(f"ix_verification_results_{column}"), table_name="verification_results"
        )
    op.drop_table("verification_results")
    for name in TIMESTAMPS:
        op.drop_column("guide_sessions", name)
    for name, _, _ in COUNTERS:
        op.drop_column("guide_sessions", name)
