"""Transactional equipment population metadata. Revision 0014."""
from alembic import op
import sqlalchemy as sa

revision = "0014_equipment_populations"
down_revision = "0013_indexed_equipment_rankings"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "equipment_population",
        sa.Column("kind", sa.Text, primary_key=True),
        sa.Column("item_id", sa.BigInteger, primary_key=True),
        sa.Column("platform", sa.Text, primary_key=True),
        sa.Column("population", sa.BigInteger, nullable=False),
        sa.CheckConstraint("kind IN ('weapon','vehicle')", name="equipment_population_kind"),
        sa.CheckConstraint("platform IN ('pc','ps4','xboxone')", name="equipment_population_platform"),
        sa.CheckConstraint("population >= 0", name="equipment_population_nonnegative"),
    )

def downgrade():
    op.drop_table("equipment_population")
