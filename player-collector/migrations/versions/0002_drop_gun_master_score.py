"""Drop unusable Gun Master score columns.

Revision ID: 0002_drop_gun_master_score
Revises: 0001_initial_schema

Live Battlelog validation established that generalStats.gunmaster remains zero
for players known to play and win Gun Master rounds. BF4PS therefore does not
retain this field as part of the detailed-statistics contract.
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_drop_gun_master_score"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("detailed_stats_current", "gun_master_score")
    op.drop_column("detailed_stats_history", "gun_master_score")


def downgrade() -> None:
    # The removed values were never considered authoritative. A downgrade can
    # restore schema compatibility, but it cannot reconstruct discarded data.
    op.add_column(
        "detailed_stats_current",
        sa.Column("gun_master_score", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "detailed_stats_history",
        sa.Column("gun_master_score", sa.BigInteger(), nullable=True),
    )
