"""Owner provider connections and usage."""

import sqlalchemy as sa
from alembic import op

revision = "f6d1a88c9201"
down_revision = "e5b8c2f41a07"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("provider_tier", sa.String(16), nullable=False, server_default="none")
    )
    for name, columns in (
        (
            "provider_bindings",
            [
                sa.Column("role", sa.String(30), nullable=False),
                sa.Column("provider_id", sa.String(40), nullable=False),
                sa.Column("model", sa.String(120), nullable=False),
                sa.Column("sealed_key", sa.JSON(), nullable=True),
                sa.UniqueConstraint("owner_id", "role"),
            ],
        ),
        (
            "provider_usage",
            [
                sa.Column("role", sa.String(30), nullable=False),
                sa.Column("provider_id", sa.String(40), nullable=False),
                sa.Column("source", sa.String(16), nullable=False),
                sa.Column("succeeded", sa.Boolean(), nullable=False),
                sa.Column("latency_ms", sa.Integer(), nullable=False),
            ],
        ),
    ):
        op.create_table(
            name,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            *columns,
        )
        op.create_index(f"ix_{name}_owner_id", name, ["owner_id"])


def downgrade():
    op.drop_table("provider_usage")
    op.drop_table("provider_bindings")
    op.drop_column("users", "provider_tier")
