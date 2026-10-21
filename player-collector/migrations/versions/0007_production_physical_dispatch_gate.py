"""Allow multiple physical HTTP dispatches within one job attempt.

Revision ID: 0007_physical_dispatch_gate
Revises: 0006_stage9c_soak_round_ledger

No production collector activation is implied by this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_physical_dispatch_gate"
down_revision = "0006_stage9c_soak_round_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_dispatches",
        sa.Column("request_ordinal", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "outbound_dispatch_request_ordinal_positive",
        "outbound_dispatches",
        "request_ordinal > 0",
    )
    op.create_unique_constraint(
        "uq_outbound_dispatch_physical_identity",
        "outbound_dispatches",
        ["job_id", "attempt_number", "resource", "lease_token", "request_ordinal"],
    )
    op.drop_constraint("uq_outbound_dispatch_identity", "outbound_dispatches", type_="unique")
    op.create_index(
        "ix_outbound_dispatch_admitted_at",
        "outbound_dispatches",
        ["admitted_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM outbound_dispatches)")).scalar_one():
        raise RuntimeError("REFUSING: outbound_dispatches contains durable dispatch evidence")
    op.drop_index("ix_outbound_dispatch_admitted_at", table_name="outbound_dispatches")
    op.create_unique_constraint(
        "uq_outbound_dispatch_identity",
        "outbound_dispatches",
        ["job_id", "attempt_number", "resource", "lease_token"],
    )
    op.drop_constraint("uq_outbound_dispatch_physical_identity", "outbound_dispatches", type_="unique")
    op.drop_constraint("outbound_dispatch_request_ordinal_positive", "outbound_dispatches", type_="check")
    op.drop_column("outbound_dispatches", "request_ordinal")
