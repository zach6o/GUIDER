"""user_feedback"""

import sqlalchemy as sa
from alembic import op

revision = "d3a5e91c72b4"
down_revision = "c7f2b41d9a88"
branch_labels = None
depends_on = None

# `verification_id` and `observed_confidence` are copied onto the row rather than
# joined at read time: the verification they describe expires, and the finding
# that the observer advanced too early at that confidence is what D05 needs to
# keep.


def upgrade():
    op.create_table(
        "user_feedback",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=True),
        sa.Column("instruction_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("verification_id", sa.String(length=36), nullable=True),
        sa.Column("observed_confidence", sa.Float(), nullable=True),
        sa.Column("control_epoch", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('incorrect_guidance', 'helpful', 'unhelpful', 'privacy_concern')",
            name="user_feedback_kind",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'reviewed', 'resolved')",
            name="user_feedback_status",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
    )
    for column in ("expires_at", "kind", "owner_id", "session_id", "step_id"):
        op.create_index(
            op.f(f"ix_user_feedback_{column}"),
            "user_feedback",
            [column],
            unique=False,
        )


def downgrade():
    for column in ("step_id", "session_id", "owner_id", "kind", "expires_at"):
        op.drop_index(op.f(f"ix_user_feedback_{column}"), table_name="user_feedback")
    op.drop_table("user_feedback")
