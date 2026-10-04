"""Add PostgreSQL-coordinated outbound request gates.

Revision ID: 0003_request_gates
Revises: 0002_drop_gun_master_score
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_request_gates"
down_revision: str | None = "0002_drop_gun_master_score"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_gates",
        sa.Column("egress_key", sa.Text(), primary_key=True),
        sa.Column("next_request_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "btrim(egress_key) <> ''",
            name="request_gates_egress_nonempty",
        ),
    )


def downgrade() -> None:
    op.drop_table("request_gates")
