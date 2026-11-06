"""Index compact lookup's block foreign key for bounded retention deletes.

Revision ID: 0025_compact_lookup_fk_idx
Revises: 0024_profile_lookup_idx
"""
from alembic import op

revision = '0025_compact_lookup_fk_idx'
down_revision = '0024_profile_lookup_idx'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            'CREATE INDEX CONCURRENTLY IF NOT EXISTS '
            'ix_rank_compact_lookup_generation_block '
            'ON public.equipment_rank_compact_lookup (generation_id, block_id)'
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            'DROP INDEX CONCURRENTLY IF EXISTS '
            'public.ix_rank_compact_lookup_generation_block'
        )
