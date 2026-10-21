"""Durable, initially inert public manual-request ledger.

Revision ID: 0009_manual_requests
Revises: 0008_runtime_budgets

This migration deliberately creates no web role, public SQL functions, or
collection jobs. The request API and scheduler require separate activation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_manual_requests"
down_revision = "0008_runtime_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_collection_requests",
        sa.Column("request_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status_detail", sa.Text()),
        sa.CheckConstraint("request_kind IN ('add','refresh')", name="manual_requests_kind_check"),
        sa.CheckConstraint("status IN ('accepted','queued','collecting','completed','retrying','rejected')", name="manual_requests_status_check"),
        sa.CheckConstraint("completed_at IS NULL OR completed_at >= requested_at", name="manual_requests_time_check"),
    )
    op.create_index("ix_manual_requests_soldier_time", "manual_collection_requests", ["soldier_id", sa.text("requested_at DESC")])
    op.create_index("ix_manual_requests_status", "manual_collection_requests", ["status", "requested_at"])
    # A single per-soldier cooldown anchor, updated only in the eventual
    # authorized transaction; avoids racing concurrent requests.
    op.create_table(
        "manual_request_cooldowns",
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_request_id", sa.BigInteger(), sa.ForeignKey("manual_collection_requests.request_id", ondelete="RESTRICT"), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("manual_request_cooldowns", "manual_collection_requests"):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():
            raise RuntimeError(f"REFUSING: {table} contains manual request evidence")
    op.drop_table("manual_request_cooldowns")
    op.drop_index("ix_manual_requests_status", table_name="manual_collection_requests")
    op.drop_index("ix_manual_requests_soldier_time", table_name="manual_collection_requests")
    op.drop_table("manual_collection_requests")