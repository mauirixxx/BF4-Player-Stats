"""Allow blocks-only format-2 snapshots with exclusion-set fingerprint.

Revision ID: 0022_compact_blocks_only_format
Revises: 0021_reconcile_player_exclusions

Additive migration; does not rewrite existing ranking data.
"""
from alembic import op
import sqlalchemy as sa

revision = '0022_compact_blocks_only_format'
down_revision = '0021_reconcile_player_exclusions'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', type_='check')
    op.create_check_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', 'snapshot_format IN (0,1,2)')
    op.add_column('equipment_rank_generations', sa.Column('exclusion_fingerprint', sa.Text(), nullable=True))
    op.create_check_constraint('ck_rank_generation_format2_fingerprint', 'equipment_rank_generations',
                               'snapshot_format <> 2 OR exclusion_fingerprint IS NOT NULL')


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text('SELECT 1 FROM equipment_rank_generations WHERE snapshot_format=2 LIMIT 1')).first():
        raise RuntimeError('retire/delete format-2 generations before downgrade')
    op.drop_constraint('ck_rank_generation_format2_fingerprint', 'equipment_rank_generations', type_='check')
    op.drop_column('equipment_rank_generations', 'exclusion_fingerprint')
    op.drop_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', type_='check')
    op.create_check_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', 'snapshot_format IN (0,1)')
