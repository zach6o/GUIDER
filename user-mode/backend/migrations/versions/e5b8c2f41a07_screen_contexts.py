"""screen_contexts"""

import sqlalchemy as sa
from alembic import op

revision = "e5b8c2f41a07"
down_revision = "d3a5e91c72b4"
branch_labels = None
depends_on = None

# Descriptions and a hash, never pixels. The digest is indexed because the common
# read is "is this the same screen as last time", and the answer decides whether a
# reasoning call happens at all.


def upgrade():
    op.create_table(
        "screen_contexts",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=True),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("application", sa.String(length=80), nullable=False),
        sa.Column("application_matches_expected", sa.Boolean(), nullable=False),
        sa.Column("screen", sa.String(length=120), nullable=False),
        sa.Column("dialog", sa.String(length=200), nullable=True),
        sa.Column("error_text", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("control_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('before_start', 'in_progress', 'step_satisfied', "
            "'later_step_satisfied', 'off_track', 'blocked_dialog', 'unreadable')",
            name="screen_contexts_stage",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "session_id"],
            ["guide_sessions.owner_id", "guide_sessions.id"],
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id"),
    )
    for column in ("digest", "expires_at", "owner_id", "session_id", "step_id"):
        op.create_index(
            op.f(f"ix_screen_contexts_{column}"),
            "screen_contexts",
            [column],
            unique=False,
        )


def downgrade():
    for column in ("step_id", "session_id", "owner_id", "expires_at", "digest"):
        op.drop_index(op.f(f"ix_screen_contexts_{column}"), table_name="screen_contexts")
    op.drop_table("screen_contexts")
