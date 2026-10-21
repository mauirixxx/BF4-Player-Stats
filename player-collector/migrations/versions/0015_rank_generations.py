"""Versioned, atomically published equipment ranking generations.

Revision ID: 0015_rank_generations
Revises: 0014_equipment_populations
"""
from alembic import op
import sqlalchemy as sa

revision = '0015_rank_generations'
down_revision = '0014_equipment_populations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('equipment_rank_generations',
        sa.Column('generation_id', sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column('kind', sa.Text, nullable=False),
        sa.Column('item_id', sa.BigInteger, nullable=False),
        sa.Column('platform', sa.Text, nullable=False),
        sa.Column('metric', sa.Text, nullable=False),
        sa.Column('status', sa.Text, nullable=False, server_default='building'),
        sa.Column('row_count', sa.BigInteger, nullable=True),
        sa.Column('input_max_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('weapon','vehicle')", name='equipment_rank_generation_kind'),
        sa.CheckConstraint("platform IN ('pc','ps4','xboxone','all')", name='equipment_rank_generation_platform'),
        sa.CheckConstraint("(kind='weapon' AND metric IN ('kills','kpm','accuracy')) OR (kind='vehicle' AND metric IN ('kills','kpm'))", name='equipment_rank_generation_metric'),
        sa.CheckConstraint("status IN ('building','validated','published','retired','failed')", name='equipment_rank_generation_status'),
        sa.CheckConstraint('row_count IS NULL OR row_count >= 0', name='equipment_rank_generation_count'))
    op.create_table('equipment_rank_rows',
        sa.Column('generation_id', sa.BigInteger, sa.ForeignKey('equipment_rank_generations.generation_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('soldier_id', sa.BigInteger, nullable=False, primary_key=True),
        sa.Column('rank', sa.BigInteger, nullable=False),
        sa.Column('position', sa.BigInteger, nullable=False),
        sa.CheckConstraint('rank >= 1 AND position >= 1', name='equipment_rank_positive'),
        sa.UniqueConstraint('generation_id','position',name='uq_equipment_rank_generation_position'))
    op.create_index('ix_equipment_rank_rows_soldier','equipment_rank_rows',['soldier_id','generation_id'])
    op.create_table('equipment_rank_published',
        sa.Column('kind',sa.Text,primary_key=True),
        sa.Column('item_id',sa.BigInteger,primary_key=True),
        sa.Column('platform',sa.Text,primary_key=True),
        sa.Column('metric',sa.Text,primary_key=True),
        sa.Column('generation_id',sa.BigInteger,sa.ForeignKey('equipment_rank_generations.generation_id'),nullable=False),
        sa.Column('published_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
        sa.CheckConstraint("kind IN ('weapon','vehicle')",name='equipment_rank_published_kind'),
        sa.CheckConstraint("platform IN ('pc','ps4','xboxone','all')",name='equipment_rank_published_platform'))


def downgrade():
    op.drop_table('equipment_rank_published')
    op.drop_table('equipment_rank_rows')
    op.drop_table('equipment_rank_generations')
