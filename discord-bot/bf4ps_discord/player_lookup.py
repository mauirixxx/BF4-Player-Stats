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
