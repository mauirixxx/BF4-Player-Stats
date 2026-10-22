"""Bounded exact current-name lookup, independent read-only statistics connection."""
import psycopg

PLATFORMS = {'PC': 'pc', 'PlayStation': 'ps4', 'Xbox': 'xboxone'}


def find_player(dsn: str, name: str, platform: str):
    if not name or len(name) > 100 or platform not in PLATFORMS.values():
        raise ValueError('Invalid player lookup')
    with psycopg.connect(dsn, connect_timeout=4, options='-c default_transaction_read_only=on -c statement_timeout=4000') as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT current_name, platform, persona_id FROM public.soldiers
                WHERE lower(current_name)=lower(%s) AND platform=%s
                ORDER BY last_seen_at DESC NULLS LAST, soldier_id DESC LIMIT 2''', (name,platform))
            return cur.fetchall()


def find_player_overview(dsn: str, name: str, platform: str):
    """Return up to two exact-name matches with their latest detailed stats."""
    if not name or len(name) > 100 or platform not in PLATFORMS.values():
        raise ValueError('Invalid player lookup')
    with psycopg.connect(dsn, connect_timeout=4,
                         options='-c default_transaction_read_only=on -c statement_timeout=4000') as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT s.current_name, s.platform, s.persona_id,
                d.rank, d.time_played_seconds, d.kills, d.deaths,
                d.shots_fired, d.shots_hit, d.highest_kill_streak,
                d.wins, d.losses, d.total_score,
                d.assault_score, d.engineer_score, d.support_score, d.recon_score,
                d.source_fetched_at, s.soldier_id
                FROM public.soldiers AS s
                LEFT JOIN public.detailed_stats_current AS d ON d.soldier_id=s.soldier_id
                WHERE lower(s.current_name)=lower(%s) AND s.platform=%s
                ORDER BY s.last_seen_at DESC NULLS LAST, s.soldier_id DESC
                LIMIT 2''', (name, platform))
            return cur.fetchall()


def find_signature_weapon(dsn: str, soldier_id: int):
    """Top weapon by recorded kills; deterministic tie-break and read-only."""
    with psycopg.connect(dsn, connect_timeout=4,
                         options='-c default_transaction_read_only=on -c statement_timeout=4000') as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT c.name, c.slug, w.kills
                FROM public.soldier_weapon_stats AS w
                JOIN public.weapon_catalog AS c ON c.weapon_id=w.weapon_id
                WHERE w.soldier_id=%s AND w.kills>0
                ORDER BY w.kills DESC, w.weapon_id ASC LIMIT 1""", (soldier_id,))
            return cur.fetchone()
