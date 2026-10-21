"""Stage-only candidate migration after 0016. NOT applied to production.

Alembic upgrade/downgrade functions, to be integrated into authoritative
migration tree after scratch validation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_rank_immutable_scores"
down_revision = "0016_rank_scope_versions"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("equipment_rank_rows", sa.Column("snapshot_kills", sa.BigInteger(), nullable=True))
    op.add_column("equipment_rank_rows", sa.Column("snapshot_kpm", sa.Numeric(), nullable=True))
    op.add_column("equipment_rank_rows", sa.Column("snapshot_accuracy", sa.Numeric(), nullable=True))
    op.add_column("equipment_rank_rows", sa.Column("snapshot_source_fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("equipment_rank_generations", sa.Column("snapshot_format", sa.SmallInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_rank_generation_snapshot_format",
                               "equipment_rank_generations", "snapshot_format IN (0,1)")

def downgrade():
    op.drop_constraint("ck_rank_generation_snapshot_format", "equipment_rank_generations", type_="check")
    op.drop_column("equipment_rank_generations", "snapshot_format")
    for column in ("snapshot_source_fetched_at", "snapshot_accuracy", "snapshot_kpm", "snapshot_kills"):
        op.drop_column("equipment_rank_rows", column)
