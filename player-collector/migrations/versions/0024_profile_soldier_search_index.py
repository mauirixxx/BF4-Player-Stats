"""Concurrent soldier-first profile link index for homepage identity search.

Revision ID: 0024_profile_soldier_search_index
Revises: 0023_compact_exclusion_guard
"""
from alembic import op

revision = '0024_profile_soldier_search_index'
down_revision = '0023_compact_exclusion_guard'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            'CREATE INDEX CONCURRENTLY IF NOT EXISTS '
            'ix_profile_soldiers_soldier_last_seen '
            'ON public.profile_soldiers (soldier_id, last_seen_at DESC)'
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            'DROP INDEX CONCURRENTLY IF EXISTS '
            'public.ix_profile_soldiers_soldier_last_seen'
        )
