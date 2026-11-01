"""Compact immutable equipment ranking blocks and soldier lookup.

Revision ID: 0020_compact_rank_snapshots
Revises: 0019_soldier_search_trigrams

Additive only: existing ranking tables and publication path remain intact.
"""
from alembic import op
import sqlalchemy as sa

revision = '0020_compact_rank_snapshots'
down_revision = '0019_soldier_search_trigrams'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'equipment_rank_compact_blocks',
        sa.Column('generation_id', sa.BigInteger(), sa.ForeignKey('equipment_rank_generations.generation_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('block_id', sa.Integer(), primary_key=True),
        sa.Column('first_position', sa.BigInteger(), nullable=False),
        sa.Column('last_position', sa.BigInteger(), nullable=False),
        sa.Column('payload', sa.LargeBinary(), nullable=False),
        sa.CheckConstraint('block_id >= 0 AND first_position >= 1 AND last_position >= first_position', name='ck_rank_compact_block_bounds'),
    )
    op.create_table(
        'equipment_rank_compact_lookup',
        sa.Column('generation_id', sa.BigInteger(), sa.ForeignKey('equipment_rank_generations.generation_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('soldier_id', sa.BigInteger(), primary_key=True),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('block_offset', sa.Integer(), nullable=False),
        sa.CheckConstraint('block_id >= 0 AND block_offset >= 0 AND block_offset < 1000', name='ck_rank_compact_lookup_bounds'),
        sa.ForeignKeyConstraint(['generation_id', 'block_id'], ['equipment_rank_compact_blocks.generation_id', 'equipment_rank_compact_blocks.block_id'], ondelete='CASCADE'),
    )
    op.create_index('ix_rank_compact_lookup_soldier', 'equipment_rank_compact_lookup', ['soldier_id', 'generation_id'])
    op.create_table(
        'equipment_rank_compact_published',
        sa.Column('kind', sa.Text(), primary_key=True),
        sa.Column('item_id', sa.BigInteger(), primary_key=True),
        sa.Column('platform', sa.Text(), primary_key=True),
        sa.Column('metric', sa.Text(), primary_key=True),
        sa.Column('generation_id', sa.BigInteger(), sa.ForeignKey('equipment_rank_generations.generation_id'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade():
    op.drop_table('equipment_rank_compact_published')
    op.drop_index('ix_rank_compact_lookup_soldier', table_name='equipment_rank_compact_lookup')
    op.drop_table('equipment_rank_compact_lookup')
    op.drop_table('equipment_rank_compact_blocks')
