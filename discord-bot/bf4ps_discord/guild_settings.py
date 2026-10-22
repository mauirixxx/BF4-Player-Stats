"""Guild-owned settings in the independent Discord control-plane database."""
import psycopg

MANAGEMENT_ROLE = 'management_role_id'

def get(dsn: str, guild_id: int) -> dict[str, str]:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT setting_key,setting_value FROM discord_guild_settings WHERE guild_id=%s',(guild_id,))
            return dict(cur.fetchall())

def set_management_role(dsn: str, guild_id: int, role_id: int | None, actor_id: int) -> None:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO discord_guilds(guild_id) VALUES (%s) ON CONFLICT (guild_id) DO NOTHING',(guild_id,))
            if role_id is None:
                cur.execute('DELETE FROM discord_guild_settings WHERE guild_id=%s AND setting_key=%s',(guild_id,MANAGEMENT_ROLE))
            else:
                cur.execute('''INSERT INTO discord_guild_settings(guild_id,setting_key,setting_value,value_type,updated_by)
                    VALUES (%s,%s,%s,'integer',%s) ON CONFLICT (guild_id,setting_key)
                    DO UPDATE SET setting_value=excluded.setting_value,updated_by=excluded.updated_by,updated_at=now()''',
                    (guild_id,MANAGEMENT_ROLE,str(role_id),actor_id))

def allowed(member, guild, settings: dict[str,str]) -> bool:
    if member.id == guild.owner_id:
        return True
    raw=settings.get(MANAGEMENT_ROLE)
    if not raw:
        return False
    try:
        configured=guild.get_role(int(raw))
        if configured is None:
            return False
        return isinstance(member, __import__('discord').Member) and member.top_role >= configured
    except (TypeError, ValueError):
        return False
