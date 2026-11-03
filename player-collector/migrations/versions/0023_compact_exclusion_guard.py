"""Add explicit active-exclusion fingerprint for blocks-only snapshots.

Revision ID: 0023_compact_exclusion_guard
Revises: 0022_compact_blocks_only_format

New recovery safety improvement, not part of the original 0022 schema.
"""
from alembic import op
import sqlalchemy as sa

revision = '0023_compact_exclusion_guard'
down_revision = '0022_compact_blocks_only_format'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('equipment_rank_generations', sa.Column('exclusion_fingerprint', sa.Text(), nullable=True))
    # Existing format-2 generations may predate this safeguard. The reader
    # rejects NULL fingerprints; do not rewrite or silently trust old data.


def downgrade():
    op.drop_column('equipment_rank_generations', 'exclusion_fingerprint')