"""Guild-owned settings in the independent Discord control-plane database."""
import psycopg
import json

MANAGEMENT_ROLE = 'management_role_id'
MINIMUM_ROLE = 'minimum_role_id'
LISTEN_CHANNELS = 'listen_channel_ids'
AUDIT_CHANNEL = 'audit_channel_id'

def get(dsn: str, guild_id: int) -> dict[str, str]:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT setting_key,setting_value FROM discord_guild_settings WHERE guild_id=%s',(guild_id,))
            return dict(cur.fetchall())

def set_role(dsn: str, guild_id: int, key: str, role_id: int | None, actor_id: int) -> None:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO discord_guilds(guild_id) VALUES (%s) ON CONFLICT (guild_id) DO NOTHING',(guild_id,))
            if role_id is None:
                cur.execute('DELETE FROM discord_guild_settings WHERE guild_id=%s AND setting_key=%s',(guild_id,key))
            else:
                cur.execute('''INSERT INTO discord_guild_settings(guild_id,setting_key,setting_value,value_type,updated_by)
                    VALUES (%s,%s,%s,'integer',%s) ON CONFLICT (guild_id,setting_key)
                    DO UPDATE SET setting_value=excluded.setting_value,updated_by=excluded.updated_by,updated_at=now()''',
                    (guild_id,key,str(role_id),actor_id))

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


def set_management_role(dsn: str, guild_id: int, role_id: int | None, actor_id: int) -> None:
    set_role(dsn,guild_id,MANAGEMENT_ROLE,role_id,actor_id)

def set_minimum_role(dsn: str, guild_id: int, role_id: int | None, actor_id: int) -> None:
    set_role(dsn,guild_id,MINIMUM_ROLE,role_id,actor_id)

def player_allowed(member, guild, settings: dict[str,str]) -> bool:
    """Fail closed for missing configured roles; admins always bypass."""
    if allowed(member,guild,settings):
        return True
    raw=settings.get(MINIMUM_ROLE)
    if not raw:
        return True
    try:
        role=guild.get_role(int(raw))
        return role is not None and isinstance(member,__import__('discord').Member) and member.top_role >= role
    except (TypeError,ValueError):
        return False


def listen_channel_ids(settings: dict[str,str]) -> set[int]:
    raw=settings.get(LISTEN_CHANNELS)
    if raw is None:
        return set()
    try:
        values=json.loads(raw)
        if not isinstance(values,list) or not values or any(type(x) is not int or x<=0 for x in values):
            raise ValueError('invalid listen channel configuration')
        return set(values)
    except (TypeError,ValueError) as exc:
        raise ValueError('invalid listen channel configuration') from exc


def player_channel_allowed(member, guild, channel_id: int, settings: dict[str,str]) -> bool:
    if allowed(member,guild,settings):
        return True
    try:
        return channel_id in listen_channel_ids(settings) if LISTEN_CHANNELS in settings else True
    except ValueError:
        return False


def update_listen_channel(dsn: str, guild_id: int, channel_id: int, add: bool, actor_id: int) -> list[int]:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO discord_guilds(guild_id) VALUES (%s) ON CONFLICT (guild_id) DO NOTHING',(guild_id,))
            cur.execute('SELECT guild_id FROM discord_guilds WHERE guild_id=%s FOR UPDATE',(guild_id,))
            cur.execute('SELECT setting_value FROM discord_guild_settings WHERE guild_id=%s AND setting_key=%s',(guild_id,LISTEN_CHANNELS))
            row=cur.fetchone()
            channels=listen_channel_ids({LISTEN_CHANNELS:row[0]}) if row else set()
            if add:
                if channel_id in channels:
                    raise ValueError("Channel already configured")
                channels.add(channel_id)
            else:
                if channel_id not in channels:
                    raise ValueError("Channel not configured")
                channels.remove(channel_id)
            if not channels:
                cur.execute('DELETE FROM discord_guild_settings WHERE guild_id=%s AND setting_key=%s',(guild_id,LISTEN_CHANNELS))
            else:
                cur.execute('''INSERT INTO discord_guild_settings(guild_id,setting_key,setting_value,value_type,updated_by)
                    VALUES (%s,%s,%s,'json',%s) ON CONFLICT (guild_id,setting_key)
                    DO UPDATE SET setting_value=excluded.setting_value,value_type='json',updated_by=excluded.updated_by,updated_at=now()''',
                    (guild_id,LISTEN_CHANNELS,json.dumps(sorted(channels)),actor_id))
            return sorted(channels)


def set_audit_channel(dsn: str, guild_id: int, channel_id: int | None, actor_id: int) -> None:
    set_role(dsn,guild_id,AUDIT_CHANNEL,channel_id,actor_id)

def change_audit_channel(dsn: str, guild_id: int, channel_id: int, setting: bool, actor_id: int) -> None:
    """Atomic compare-and-set prevents duplicates and stale removals."""
    with psycopg.connect(dsn,connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO discord_guilds(guild_id) VALUES (%s) ON CONFLICT (guild_id) DO NOTHING',(guild_id,))
            cur.execute('SELECT guild_id FROM discord_guilds WHERE guild_id=%s FOR UPDATE',(guild_id,))
            cur.execute('SELECT setting_value FROM discord_guild_settings WHERE guild_id=%s AND setting_key=%s',(guild_id,AUDIT_CHANNEL))
            row=cur.fetchone()
            current=row[0] if row else None
            if setting:
                if current==str(channel_id):
                    raise ValueError('Channel already configured')
                cur.execute("INSERT INTO discord_guild_settings(guild_id,setting_key,setting_value,value_type,updated_by) VALUES (%s,%s,%s,'integer',%s) ON CONFLICT (guild_id,setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_by=excluded.updated_by,updated_at=now()",(guild_id,AUDIT_CHANNEL,str(channel_id),actor_id))
            else:
                if current!=str(channel_id):
                    raise ValueError('Channel not configured')
                cur.execute('DELETE FROM discord_guild_settings WHERE guild_id=%s AND setting_key=%s',(guild_id,AUDIT_CHANNEL))
