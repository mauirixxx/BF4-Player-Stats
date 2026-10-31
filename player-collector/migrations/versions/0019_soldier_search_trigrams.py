"""Concurrent trigram indexes for bounded global soldier substring search.

Revision ID: 0019_soldier_search_trigrams
Revises: 0018_distributed_rank_queue
"""
from alembic import op

revision = '0019_soldier_search_trigrams'
down_revision = '0018_distributed_rank_queue'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_soldiers_current_name_trgm ON public.soldiers USING gin (lower(current_name) gin_trgm_ops)')
        op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_soldier_names_name_trgm ON public.soldier_names USING gin (lower(name) gin_trgm_ops)')


def downgrade():
    with op.get_context().autocommit_block():
        op.execute('DROP INDEX CONCURRENTLY IF EXISTS public.ix_soldier_names_name_trgm')
        op.execute('DROP INDEX CONCURRENTLY IF EXISTS public.ix_soldiers_current_name_trgm')
