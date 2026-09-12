"""instructions_and_completion_claims"""

import sqlalchemy as sa
from alembic import op

revision = "174286596589"
down_revision = "acb7c3b71e9c"
branch_labels = None
depends_on = None

OWNER_STEP = (
    ["owner_id", "step_id"],
    ["task_steps.owner_id", "task_steps.id"],
)
OWNER_SESSION = (
    ["owner_id", "session_id"],
    ["guide_sessions.owner_id", "guide_sessions.id"],
)


def upgrade():
    op.create_table(
        "instructions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("what", sa.String(length=1000), nullable=False),
        sa.Column("where", sa.String(length=300), nullable=False),
        sa.Column("why", sa.String(length=500), nullable=True),
        sa.Column("confirmation_hint", sa.String(length=300), nullable=False),
        sa.Column("cannot_find_hint", sa.String(length=300), nullable=False),
        sa.Column("pointer", sa.JSON(), nullable=True),
        sa.Column("control_epoch", sa.BigInteger(), nullable=False),
        sa.Column("evidence_available", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready', 'superseded', 'invalidated')", name="instructions_status"
        ),
        sa.CheckConstraint("version >= 1", name="instructions_version"),
        sa.ForeignKeyConstraint(*OWNER_SESSION),
        sa.ForeignKeyConstraint(*OWNER_STEP, ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
        sa.UniqueConstraint("owner_id", "step_id", "version"),
    )
    for column in ("expires_at", "owner_id", "session_id", "step_id"):
        op.create_index(
            op.f(f"ix_instructions_{column}"), "instructions", [column], unique=False
        )

    op.create_table(
        "completion_claims",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("statement", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("instruction_version", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('user_claimed', 'superseded')", name="completion_claims_status"
        ),
        sa.ForeignKeyConstraint(*OWNER_SESSION),
        sa.ForeignKeyConstraint(*OWNER_STEP, ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
    )
    for column in ("owner_id", "session_id", "step_id"):
        op.create_index(
            op.f(f"ix_completion_claims_{column}"), "completion_claims", [column], unique=False
        )


def downgrade():
    for column in ("step_id", "session_id", "owner_id"):
        op.drop_index(op.f(f"ix_completion_claims_{column}"), table_name="completion_claims")
    op.drop_table("completion_claims")
    for column in ("step_id", "session_id", "owner_id", "expires_at"):
        op.drop_index(op.f(f"ix_instructions_{column}"), table_name="instructions")
    op.drop_table("instructions")
