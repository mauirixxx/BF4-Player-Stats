"""Durable distributed ranking queue and serialized global admission.

Revision ID: 0018_distributed_rank_queue
Revises: 0017_rank_immutable_scores
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_distributed_rank_queue"
down_revision = "0017_rank_immutable_scores"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "equipment_rank_capacity",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("max_active_builds", sa.Integer, nullable=False, server_default="1"),
        sa.Column("lease_seconds", sa.Integer, nullable=False, server_default="180"),
        sa.CheckConstraint("id = 1", name="ck_rank_capacity_singleton"),
        sa.CheckConstraint("max_active_builds >= 0", name="ck_rank_capacity_nonnegative"),
        sa.CheckConstraint("lease_seconds BETWEEN 30 AND 3600", name="ck_rank_lease_bounds"),
    )
    op.execute("INSERT INTO equipment_rank_capacity(id,max_active_builds,lease_seconds) VALUES(1,1,180)")
    op.create_table(
        "equipment_rank_workers",
        sa.Column("worker_id", sa.Uuid, primary_key=True),
        sa.Column("hostname", sa.Text, nullable=False),
        sa.Column("site", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "equipment_rank_jobs",
        sa.Column("kind", sa.Text, primary_key=True),
        sa.Column("item_id", sa.BigInteger, primary_key=True),
        sa.Column("platform", sa.Text, primary_key=True),
        sa.Column("metric", sa.Text, primary_key=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("claimed_by", sa.Uuid, sa.ForeignKey("equipment_rank_workers.worker_id")),
        sa.Column("claim_token", sa.Uuid),
        sa.Column("claim_epoch", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('weapon','vehicle')", name="ck_rank_job_kind"),
        sa.CheckConstraint("platform IN ('all','pc','ps4','xboxone')", name="ck_rank_job_platform"),
        sa.CheckConstraint("(kind='weapon' AND metric IN ('kills','kpm','accuracy')) OR (kind='vehicle' AND metric IN ('kills','kpm'))", name="ck_rank_job_metric"),
    )
    op.create_index("ix_rank_jobs_due", "equipment_rank_jobs", ["next_due_at"])
    op.create_index("ix_rank_jobs_lease", "equipment_rank_jobs", ["lease_expires_at"])

def downgrade():
    op.drop_index("ix_rank_jobs_lease", table_name="equipment_rank_jobs")
    op.drop_index("ix_rank_jobs_due", table_name="equipment_rank_jobs")
    op.drop_table("equipment_rank_jobs")
    op.drop_table("equipment_rank_workers")
    op.drop_table("equipment_rank_capacity")
