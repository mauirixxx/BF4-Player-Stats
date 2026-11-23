"""Store independent Battlefield Agency and BF4DB ban verification results.

Revision ID: 0027_soldier_ban_status
Revises: 0026_general_rank_snapshots

Nullable booleans distinguish unverified from confirmed not banned. This
migration creates no rows, makes no external API calls, and changes no
collector scheduling or existing soldier records.
"""
from alembic import op
import sqlalchemy as sa

revision = '0027_soldier_ban_status'
down_revision = '0026_general_rank_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'soldier_ban_status',
        sa.Column('soldier_id', sa.BigInteger(), sa.ForeignKey('soldiers.soldier_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('ba_banned', sa.Boolean(), nullable=True),
        sa.Column('bf4db_banned', sa.Boolean(), nullable=True),
        sa.Column('ba_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bf4db_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('agency_player_uuid', sa.Uuid(), nullable=True),
        sa.Column('ba_reason', sa.Text(), nullable=True),
        sa.Column('bf4db_reason', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade():
    op.drop_table('soldier_ban_status')
