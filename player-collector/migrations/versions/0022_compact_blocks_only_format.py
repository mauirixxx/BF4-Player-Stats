"""Permit blocks-only compact snapshot format 2.

Revision ID: 0022_compact_blocks_only_format
Revises: 0021_reconcile_player_exclusions

Matches the recovered scratch-database constraint at revision 0022.
"""
from alembic import op

revision = '0022_compact_blocks_only_format'
down_revision = '0021_reconcile_player_exclusions'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', type_='check')
    op.create_check_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', 'snapshot_format IN (0,1,2)')


def downgrade():
    op.drop_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', type_='check')
    op.create_check_constraint('ck_rank_generation_snapshot_format', 'equipment_rank_generations', 'snapshot_format IN (0,1)')
