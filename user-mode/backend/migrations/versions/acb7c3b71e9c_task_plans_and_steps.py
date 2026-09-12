"""task_plans_and_steps"""

import sqlalchemy as sa
from alembic import op

revision = "acb7c3b71e9c"
down_revision = "ffc3f8107658"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_plans",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(length=36), nullable=True),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'superseded')", name="task_plans_status"
        ),
        sa.CheckConstraint("version >= 1", name="task_plans_version"),
        sa.ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "task_id"],
            ["guide_tasks.owner_id", "guide_tasks.id"],
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
        sa.UniqueConstraint("owner_id", "session_id", "version"),
    )
    op.create_index(op.f("ix_task_plans_expires_at"), "task_plans", ["expires_at"], unique=False)
    op.create_index(op.f("ix_task_plans_owner_id"), "task_plans", ["owner_id"], unique=False)
    op.create_index(op.f("ix_task_plans_session_id"), "task_plans", ["session_id"], unique=False)
    op.create_index(op.f("ix_task_plans_task_id"), "task_plans", ["task_id"], unique=False)
    op.create_table(
        "task_steps",
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("previous_step_id", sa.String(length=36), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=1000), nullable=False),
        sa.Column("expected_result", sa.String(length=500), nullable=False),
        sa.Column("success_criterion", sa.String(length=500), nullable=False),
        sa.Column("fallback", sa.String(length=500), nullable=False),
        sa.Column("explanation", sa.String(length=1000), nullable=False),
        sa.Column("application_key", sa.String(length=80), nullable=False),
        sa.Column("risk", sa.String(), nullable=False),
        sa.Column("policy_disposition", sa.String(), nullable=False),
        sa.Column("evidence_kind", sa.String(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_kind IN ('visual', 'text', 'self_report')", name="task_steps_evidence"
        ),
        sa.CheckConstraint(
            "policy_disposition IN ('allow', 'confirm', 'block')", name="task_steps_disposition"
        ),
        sa.CheckConstraint("risk IN ('low', 'medium', 'high')", name="task_steps_risk"),
        sa.CheckConstraint(
            "status IN ('pending', 'instruction_ready', 'awaiting_user_action', 'user_claimed', "
            "'verified', 'blocked', 'skipped', 'superseded')",
            name="task_steps_status",
        ),
        sa.CheckConstraint("ordinal >= 1 AND ordinal <= 12", name="task_steps_ordinal"),
        sa.ForeignKeyConstraint(
            ["owner_id", "plan_id"],
            ["task_plans.owner_id", "task_plans.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
        sa.UniqueConstraint("owner_id", "plan_id", "ordinal"),
    )
    op.create_index(op.f("ix_task_steps_owner_id"), "task_steps", ["owner_id"], unique=False)
    op.create_index(op.f("ix_task_steps_plan_id"), "task_steps", ["plan_id"], unique=False)
    op.create_index(op.f("ix_task_steps_session_id"), "task_steps", ["session_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_task_steps_session_id"), table_name="task_steps")
    op.drop_index(op.f("ix_task_steps_plan_id"), table_name="task_steps")
    op.drop_index(op.f("ix_task_steps_owner_id"), table_name="task_steps")
    op.drop_table("task_steps")
    op.drop_index(op.f("ix_task_plans_task_id"), table_name="task_plans")
    op.drop_index(op.f("ix_task_plans_session_id"), table_name="task_plans")
    op.drop_index(op.f("ix_task_plans_owner_id"), table_name="task_plans")
    op.drop_index(op.f("ix_task_plans_expires_at"), table_name="task_plans")
    op.drop_table("task_plans")
