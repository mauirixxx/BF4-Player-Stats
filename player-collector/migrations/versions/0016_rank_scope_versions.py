"""Transactional scope invalidation for equipment ranking generations.

Revision ID: 0016_rank_scope_versions
Revises: 0015_rank_generations
"""
from alembic import op
import sqlalchemy as sa

revision='0016_rank_scope_versions'
down_revision='0015_rank_generations'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('equipment_rank_scope_versions',
        sa.Column('kind',sa.Text,primary_key=True),
        sa.Column('item_id',sa.BigInteger,primary_key=True),
        sa.Column('platform',sa.Text,primary_key=True),
        sa.Column('version',sa.BigInteger,nullable=False,server_default='0'),
        sa.Column('changed_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
        sa.CheckConstraint("kind IN ('weapon','vehicle')",name='equipment_rank_scope_kind'),
        sa.CheckConstraint("platform IN ('pc','ps4','xboxone','all')",name='equipment_rank_scope_platform'),
        sa.CheckConstraint('version >= 0',name='equipment_rank_scope_version_nonnegative'))
    op.add_column('equipment_rank_generations',sa.Column('input_scope_version',sa.BigInteger,nullable=True))
    op.create_check_constraint('equipment_rank_generation_input_version','equipment_rank_generations',
                               'input_scope_version IS NULL OR input_scope_version >= 0')


def downgrade():
    op.drop_constraint('equipment_rank_generation_input_version','equipment_rank_generations',type_='check')
    op.drop_column('equipment_rank_generations','input_scope_version')
    op.drop_table('equipment_rank_scope_versions')
