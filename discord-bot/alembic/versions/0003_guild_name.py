"""Persist human-readable Discord guild names.

Revision ID: 0003_guild_name
Revises: 0002_command_audit
"""
from alembic import op

revision = "0003_guild_name"
down_revision = "0002_command_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE discord_guilds ADD COLUMN guild_name text")
    op.execute("GRANT UPDATE (guild_name, last_seen_at, removed_at) ON discord_guilds TO bf4ps_discord_app")


def downgrade():
    raise RuntimeError("Do not automatically remove recorded guild names")
