"""Stage 9C fenced supervision runs (no activation or data backfill).

Revision ID: 0004_stage9c_supervision_runs
Revises: 0003_request_gates
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_stage9c_supervision_runs"
down_revision = "0003_request_gates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage9c_supervision_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("cutover_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("since_event_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("watchdog_owner", postgresql.UUID(as_uuid=True)),
        sa.Column("watchdog_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("abort_at", sa.DateTime(timezone=True)),
        sa.Column("abort_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("state IN ('prepared', 'active', 'aborted', 'completed')", name="stage9c_run_state"),
        sa.CheckConstraint("since_event_id >= 0", name="stage9c_run_boundary"),
        sa.CheckConstraint("watchdog_generation >= 0", name="stage9c_run_generation"),
        sa.CheckConstraint(
            "(started_at IS NULL AND deadline_at IS NULL) OR "
            "(started_at IS NOT NULL AND deadline_at = started_at + interval '6 hours')",
            name="stage9c_run_six_hour_deadline",
        ),
        sa.CheckConstraint(
            "state = 'prepared' OR (started_at IS NOT NULL AND deadline_at IS NOT NULL)",
            name="stage9c_run_activation_dates",
        ),
        sa.CheckConstraint(
            "state <> 'active' OR "
            "(watchdog_owner IS NOT NULL AND heartbeat_at IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND lease_expires_at > heartbeat_at)",
            name="stage9c_run_active_lease",
        ),
        sa.CheckConstraint(
            "(abort_at IS NULL AND abort_reason IS NULL) OR "
            "(abort_at IS NOT NULL AND abort_reason IS NOT NULL AND btrim(abort_reason) <> '')",
            name="stage9c_run_abort_pair",
        ),
        sa.CheckConstraint(
            "state <> 'aborted' OR abort_at IS NOT NULL",
            name="stage9c_run_aborted_reason",
        ),
    )
    op.create_index(
        "uq_stage9c_one_active_run",
        "stage9c_supervision_runs",
        ["state"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_stage9c_one_active_run", table_name="stage9c_supervision_runs")
    op.drop_table("stage9c_supervision_runs")
