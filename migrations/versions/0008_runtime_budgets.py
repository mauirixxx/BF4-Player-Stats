"""Database-managed fleet dispatch and background admission budgets.

Revision ID: 0008_runtime_budgets
Revises: 0007_physical_dispatch_gate
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_runtime_budgets"
down_revision = "0007_physical_dispatch_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_budgets",
        sa.Column("singleton", sa.Boolean(), primary_key=True, server_default=sa.true()),
        sa.Column("physical_dispatches_per_hour", sa.Integer(), nullable=False),
        sa.Column("background_slots_per_hour", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("singleton = true", name="runtime_budgets_singleton"),
        sa.CheckConstraint("physical_dispatches_per_hour BETWEEN 1 AND 5760", name="runtime_budgets_physical_range"),
        sa.CheckConstraint("background_slots_per_hour BETWEEN 1 AND physical_dispatches_per_hour", name="runtime_budgets_background_range"),
    )
    op.execute(
        "INSERT INTO runtime_budgets (singleton, physical_dispatches_per_hour, background_slots_per_hour) "
        "VALUES (true, 4800, 4800)"
    )


def downgrade() -> None:
    op.drop_table("runtime_budgets")
