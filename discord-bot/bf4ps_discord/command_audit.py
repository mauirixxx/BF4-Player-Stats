"""Write-only command audit persistence; independent of Discord log channels."""
import psycopg


def record(dsn, *, interaction_id, guild_id, channel_id, user_id,
           command_name, outcome, reason, duration_ms, invoked_at, node_id):
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO discord_command_logs
                   (interaction_id,guild_id,channel_id,user_id,command_name,
                    outcome,reason,duration_ms,invoked_at,node_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (interaction_id) DO NOTHING""",
                (interaction_id, guild_id, channel_id, user_id,
                 command_name, outcome, reason, duration_ms, invoked_at, node_id),
            )
