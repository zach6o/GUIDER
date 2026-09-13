"""imported_conversations"""

import sqlalchemy as sa
from alembic import op

revision = "b1c9a4e77d20"
down_revision = "8f570e149316"
branch_labels = None
depends_on = None

# One table, additive, reversible by dropping it. The transcript is stored once
# for provenance; nothing here grants it any authority (ADR-018).


def upgrade():
    op.create_table(
        "imported_conversations",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("transcript", sa.String(length=32768), nullable=False),
        sa.Column("redactions", sa.Integer(), nullable=False),
        sa.Column("extracted_goal", sa.String(length=4000), nullable=False),
        sa.Column("steps_extracted", sa.Integer(), nullable=False),
        sa.Column("steps_blocked", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('chatgpt', 'claude', 'gemini', 'other')",
            name="imported_conversations_source",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "task_id"],
            ["guide_tasks.owner_id", "guide_tasks.id"],
            ondelete="CASCADE",
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
    for column in ("expires_at", "owner_id", "session_id", "task_id"):
        op.create_index(
            op.f(f"ix_imported_conversations_{column}"),
            "imported_conversations",
            [column],
            unique=False,
        )


def downgrade():
    for column in ("task_id", "session_id", "owner_id", "expires_at"):
        op.drop_index(
            op.f(f"ix_imported_conversations_{column}"), table_name="imported_conversations"
        )
    op.drop_table("imported_conversations")
