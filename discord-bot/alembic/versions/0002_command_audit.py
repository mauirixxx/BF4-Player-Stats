"""Persist Discord command audit history independently of optional channel logs.

Revision ID: 0002_command_audit
Revises: 0001_discord_initial
"""
from alembic import op

revision = "0002_command_audit"
down_revision = "0001_discord_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE discord_command_logs (
            interaction_id bigint PRIMARY KEY,
            guild_id bigint,
            channel_id bigint,
            user_id bigint NOT NULL,
            command_name text NOT NULL,
            outcome text NOT NULL,
            reason text,
            duration_ms integer,
            invoked_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz NOT NULL DEFAULT now(),
            node_id text NOT NULL,
            CONSTRAINT discord_command_logs_duration_check CHECK (duration_ms IS NULL OR duration_ms >= 0)
        )
    """)
    op.execute("CREATE INDEX discord_command_logs_guild_time_idx ON discord_command_logs(guild_id, completed_at DESC)")
    op.execute("CREATE INDEX discord_command_logs_user_time_idx ON discord_command_logs(user_id, completed_at DESC)")
    op.execute("GRANT INSERT, SELECT ON discord_command_logs TO bf4ps_discord_app")


def downgrade():
    raise RuntimeError("Command audit history must not be dropped automatically")
