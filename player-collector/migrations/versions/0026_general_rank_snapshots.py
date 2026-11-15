"""Independent immutable general soldier ranking snapshots (not activated).

Revision ID: 0026_general_rank_snapshots
Revises: 0025_compact_lookup_fk_idx
"""
from alembic import op
import sqlalchemy as sa

revision = '0026_general_rank_snapshots'
down_revision = '0025_compact_lookup_fk_idx'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'general_rank_generations',
        sa.Column('generation_id', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('metric', sa.Text(), nullable=False),
        sa.Column('platform', sa.Text(), nullable=False),
        sa.Column('population', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('population >= 0', name='ck_general_rank_population'),
        sa.CheckConstraint("platform IN ('all','pc','ps4','xboxone')", name='ck_general_rank_platform'),
        sa.CheckConstraint("metric IN ('kills','total_score','wins','time_played_seconds','conquest_score','rush_score','team_deathmatch_score','domination_score','obliteration_score','defuse_score','capture_the_flag_score','air_superiority_score','carrier_assault_score','chain_link_score')", name='ck_general_rank_metric'),
    )
    op.create_table(
        'general_rank_rows',
        sa.Column('generation_id', sa.BigInteger(), sa.ForeignKey('general_rank_generations.generation_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('position', sa.BigInteger(), primary_key=True),
        sa.Column('soldier_id', sa.BigInteger(), nullable=False),
        sa.Column('value', sa.BigInteger(), nullable=False),
        sa.Column('rank', sa.BigInteger(), nullable=False),
        sa.Column('division', sa.SmallInteger(), nullable=False),
        sa.Column('hours_source_seconds', sa.BigInteger()),
        sa.CheckConstraint('position > 0 AND rank > 0 AND rank <= position', name='ck_general_rank_row_position'),
        sa.CheckConstraint('division BETWEEN 1 AND 10', name='ck_general_rank_row_division'),
        sa.UniqueConstraint('generation_id','soldier_id', name='uq_general_rank_row_soldier'),
    )
    op.create_index('ix_general_rank_rows_division_position','general_rank_rows',['generation_id','division','position'])
    op.create_table(
        'general_rank_published',
        sa.Column('metric', sa.Text(), primary_key=True),
        sa.Column('platform', sa.Text(), primary_key=True),
        sa.Column('generation_id', sa.BigInteger(), sa.ForeignKey('general_rank_generations.generation_id'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade():
    op.drop_table('general_rank_published')
    op.drop_index('ix_general_rank_rows_division_position',table_name='general_rank_rows')
    op.drop_table('general_rank_rows')
    op.drop_table('general_rank_generations')
