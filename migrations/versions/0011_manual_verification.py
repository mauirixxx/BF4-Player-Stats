"""Pending Battlelog soldier verification, without network access or activation.

Revision ID: 0011_manual_verification
Revises: 0010_manual_api_function
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_manual_verification"
down_revision = "0010_manual_api_function"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_soldier_verifications",
        sa.Column("verification_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("submitted_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("collector_uuid", sa.Uuid()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id")),
        sa.Column("last_error", sa.Text()),
        sa.CheckConstraint("persona_id > 0", name="manual_verify_persona_positive"),
        sa.CheckConstraint("platform IN ('pc','ps4','xboxone')", name="manual_verify_platform_check"),
        sa.CheckConstraint("status IN ('pending','claimed','verified','rejected')", name="manual_verify_status_check"),
        sa.CheckConstraint("attempt_count >= 0", name="manual_verify_attempt_count_check"),
        sa.UniqueConstraint("persona_id", "platform", name="uq_manual_verify_identity"),
    )
    op.create_index("ix_manual_verify_claim", "manual_soldier_verifications", ["status", "submitted_at"])
    op.execute("REVOKE ALL ON manual_soldier_verifications FROM PUBLIC")


def downgrade():
    op.drop_index("ix_manual_verify_claim", table_name="manual_soldier_verifications")
    op.drop_table("manual_soldier_verifications")
