"""Derived indexed equipment leaderboard read models (inert until populated).

Revision ID: 0013_indexed_equipment_rankings
Revises: 0012_manual_verify_api
"""
from alembic import op
import sqlalchemy as sa

revision = '0013_indexed_equipment_rankings'
down_revision = '0012_manual_verify_api'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('weapon_leaderboard_metrics',
        sa.Column('soldier_id', sa.BigInteger, sa.ForeignKey('soldiers.soldier_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('weapon_id', sa.BigInteger, sa.ForeignKey('weapon_catalog.weapon_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('kills', sa.BigInteger, nullable=False),
        sa.Column('kpm', sa.Numeric, nullable=True),
        sa.Column('accuracy', sa.Numeric, nullable=True),
        sa.Column('source_fetched_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('vehicle_leaderboard_metrics',
        sa.Column('soldier_id', sa.BigInteger, sa.ForeignKey('soldiers.soldier_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('vehicle_id', sa.BigInteger, sa.ForeignKey('vehicle_catalog.vehicle_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('kills', sa.BigInteger, nullable=False),
        sa.Column('kpm', sa.Numeric, nullable=True),
        sa.Column('source_fetched_at', sa.DateTime(timezone=True), nullable=False))
    for table, item, metrics in [('weapon_leaderboard_metrics','weapon_id',('kills','kpm','accuracy')),('vehicle_leaderboard_metrics','vehicle_id',('kills','kpm'))]:
        for metric in metrics:
            op.create_index(f'ix_{table}_{metric}_top',table,[item,sa.text(f'{metric} DESC NULLS LAST'),'soldier_id'])


def downgrade():
    op.drop_table('vehicle_leaderboard_metrics')
    op.drop_table('weapon_leaderboard_metrics')
