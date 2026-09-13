"""session_summaries"""

import sqlalchemy as sa
from alembic import op

revision = "c7f2b41d9a88"
down_revision = "b1c9a4e77d20"
branch_labels = None
depends_on = None

# Verified and self-reported steps are separate columns on purpose: a summary
# that could not tell them apart would be the one place the distinction the rest
# of the system maintains gets quietly lost (ADR-010).


def upgrade():
    op.create_table(
        "session_summaries",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("verified_steps", sa.JSON(), nullable=False),
        sa.Column("unverified_steps", sa.JSON(), nullable=False),
        sa.Column("corrections", sa.JSON(), nullable=False),
        sa.Column("text", sa.String(length=4000), nullable=False),
        sa.Column("next_action", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('achieved', 'user_reported', 'stopped', 'failed', 'expired')",
            name="session_summaries_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
        sa.UniqueConstraint("owner_id", "session_id"),
    )
    for column in ("expires_at", "owner_id", "session_id"):
        op.create_index(
            op.f(f"ix_session_summaries_{column}"),
            "session_summaries",
            [column],
            unique=False,
        )


def downgrade():
    for column in ("session_id", "owner_id", "expires_at"):
        op.drop_index(op.f(f"ix_session_summaries_{column}"), table_name="session_summaries")
    op.drop_table("session_summaries")
