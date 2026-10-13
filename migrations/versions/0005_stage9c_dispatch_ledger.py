"""Stage 9C inert dispatch ledger foundation; no collector activation.

Revision ID: 0005_stage9c_dispatch_ledger
Revises: 0004_stage9c_supervision_runs

DDL only. Admission policy and actual-send guarantee remain unimplemented.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_stage9c_dispatch_ledger"
down_revision = "0004_stage9c_supervision_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_dispatches",
        sa.Column("dispatch_id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Deliberately NO job FK: the queue row can be deleted or reclaimed.
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collector_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("egress_key", sa.Text(), nullable=False),
        sa.Column("lane", sa.Text(), nullable=False),
        sa.Column("payload_fingerprint", sa.Text(), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False, server_default="admitted"),
        sa.Column("send_marked_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "job_id", "attempt_number", "resource", "lease_token",
            name="uq_outbound_dispatch_identity",
        ),
        sa.CheckConstraint("job_id > 0 AND attempt_number > 0", name="outbound_dispatch_attempt_positive"),
        sa.CheckConstraint(
            "resource IN ('detailed','profile','weapons','vehicles')",
            name="outbound_dispatch_resource",
        ),
        sa.CheckConstraint(
            "lane IN ('background','interactive')", name="outbound_dispatch_lane",
        ),
        sa.CheckConstraint(
            "btrim(egress_key) <> '' AND btrim(payload_fingerprint) <> ''",
            name="outbound_dispatch_nonempty",
        ),
        sa.CheckConstraint(
            "phase IN ('admitted','may_have_sent','acknowledged','ambiguous')",
            name="outbound_dispatch_phase",
        ),
        sa.CheckConstraint(
            "(phase = 'admitted' AND send_marked_at IS NULL AND acknowledged_at IS NULL) "
            "OR (phase IN ('may_have_sent','ambiguous') AND send_marked_at IS NOT NULL "
            "AND acknowledged_at IS NULL) "
            "OR (phase = 'acknowledged' AND send_marked_at IS NOT NULL "
            "AND acknowledged_at IS NOT NULL)",
            name="outbound_dispatch_phase_timestamps",
        ),
        sa.CheckConstraint(
            "send_marked_at IS NULL OR send_marked_at >= admitted_at",
            name="outbound_dispatch_send_after_admit",
        ),
        sa.CheckConstraint(
            "acknowledged_at IS NULL OR acknowledged_at >= send_marked_at",
            name="outbound_dispatch_ack_after_send",
        ),
    )
    op.create_index(
        "ix_outbound_dispatch_background_admitted",
        "outbound_dispatches",
        ["admitted_at"],
        postgresql_where=sa.text("lane = 'background'"),
    )
    op.create_index(
        "ix_outbound_dispatch_egress_admitted",
        "outbound_dispatches",
        ["egress_key", "admitted_at"],
    )


def downgrade() -> None:
    # Explicitly refuse to destroy durable send evidence.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM outbound_dispatches)")).scalar_one():
        raise RuntimeError("REFUSING: outbound_dispatches contains dispatch evidence")
    op.drop_index("ix_outbound_dispatch_egress_admitted", table_name="outbound_dispatches")
    op.drop_index("ix_outbound_dispatch_background_admitted", table_name="outbound_dispatches")
    op.drop_table("outbound_dispatches")
