"""Stage 9C D2 three-hour soak run/round attribution ledger.

Revision ID: 0006_stage9c_soak_round_ledger
Revises: 0005_stage9c_dispatch_ledger

Schema only. This migration must be applied ONLY to the isolated D2 scratch
database after explicit preflight. No production database deployment.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_stage9c_soak_round_ledger"
down_revision = "0005_stage9c_dispatch_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "soak_runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column("cohort_digest", sa.Text(), nullable=False),
        sa.Column("baseline_event_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_ceiling", sa.Integer(), nullable=False),
        sa.Column("site_attempt_ceiling", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("state", sa.Text(), nullable=False, server_default="prepared"),
        sa.Column("stop_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("baseline_event_id >= 0 AND attempt_ceiling > 0 AND site_attempt_ceiling > 0", name="soak_run_bounds"),
        sa.CheckConstraint("state IN ('prepared','running','stopping','completed','failed','stopped')", name="soak_run_state"),
        sa.CheckConstraint("(start_at IS NULL AND deadline_at IS NULL) OR (start_at IS NOT NULL AND deadline_at > start_at)", name="soak_run_times"),
    )
    op.create_table(
        "soak_rounds",
        sa.Column("run_id", sa.Text(), sa.ForeignKey("soak_runs.run_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="planned"),
        sa.Column("enqueued_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("run_id", "round_number"),
        sa.CheckConstraint("round_number BETWEEN 1 AND 12", name="soak_round_number"),
        sa.CheckConstraint("state IN ('planned','enqueued','completed','failed')", name="soak_round_state"),
        sa.CheckConstraint("(state='planned' AND enqueued_at IS NULL AND completed_at IS NULL) OR (state='enqueued' AND enqueued_at IS NOT NULL AND completed_at IS NULL) OR (state IN ('completed','failed') AND enqueued_at IS NOT NULL)", name="soak_round_timestamps"),
    )
    op.create_table(
        "soak_round_jobs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("soldier_id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["run_id", "round_number"], ["soak_rounds.run_id", "soak_rounds.round_number"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("run_id", "round_number", "soldier_id"),
        sa.UniqueConstraint("job_id", name="uq_soak_round_job_id"),
        sa.CheckConstraint("job_id > 0", name="soak_job_positive"),
        sa.CheckConstraint("outcome IN ('pending','success','failed','abandoned')", name="soak_job_outcome"),
    )
    op.create_index("ix_soak_round_jobs_round", "soak_round_jobs", ["run_id", "round_number"])


def downgrade() -> None:
    op.drop_index("ix_soak_round_jobs_round", table_name="soak_round_jobs")
    op.drop_table("soak_round_jobs")
    op.drop_table("soak_rounds")
    op.drop_table("soak_runs")
