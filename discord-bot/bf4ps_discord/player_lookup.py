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


def find_signature_equipment(dsn: str, soldier_id: int):
    """Highest-kill weapon or vehicle, without summing catalog variants.

    Returns (kind, localization_key, display_slug, kills). Each category
    uses an indexed, bounded top-1 query; ties favor weapons and stable IDs.
    """
    with psycopg.connect(dsn, connect_timeout=4,
                         options='-c default_transaction_read_only=on -c statement_timeout=4000') as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT kind, name, slug, kills FROM (
                (SELECT 'weapon'::text AS kind, c.name, c.slug, w.kills, w.weapon_id AS item_id
                 FROM public.soldier_weapon_stats AS w
                 JOIN public.weapon_catalog AS c ON c.weapon_id=w.weapon_id
                 WHERE w.soldier_id=%s AND w.kills>0
                 ORDER BY w.kills DESC, w.weapon_id ASC LIMIT 1)
                UNION ALL
                (SELECT 'vehicle'::text AS kind, c.name, c.slug, v.kills, v.vehicle_id AS item_id
                 FROM public.soldier_vehicle_stats AS v
                 JOIN public.vehicle_catalog AS c ON c.vehicle_id=v.vehicle_id
                 WHERE v.soldier_id=%s AND v.kills>0
                 ORDER BY v.kills DESC, v.vehicle_id ASC LIMIT 1)
            ) AS candidates
            ORDER BY kills DESC, kind ASC, item_id ASC LIMIT 1""",
                        (soldier_id, soldier_id))
            return cur.fetchone()


def find_top_equipment(dsn: str, soldier_id: int, kind: str):
    """Return up to nine top-kill weapons or vehicles from documented current tables.

    Each record: (localization_key, slug, kills, equipped_seconds, fetched_at).
    Duplicate localization-key variants are deduplicated by highest kills, never summed.
    """
    if kind not in ("weapons", "vehicles"):
        raise ValueError("Invalid equipment view")
    if kind == "weapons":
        query = """SELECT name, slug, kills, item_seconds, source_fetched_at FROM (
                SELECT c.name, c.slug, s.kills, s.time_equipped_seconds AS item_seconds,
                    s.source_fetched_at, s.weapon_id AS item_id,
                    ROW_NUMBER() OVER (PARTITION BY c.name ORDER BY s.kills DESC, s.weapon_id) AS rn
                FROM public.soldier_weapon_stats AS s
                JOIN public.weapon_catalog AS c ON c.weapon_id=s.weapon_id
                WHERE s.soldier_id=%s AND s.kills>0
            ) AS ranked WHERE rn=1 ORDER BY kills DESC, item_id LIMIT 9"""
    else:
        query = """SELECT name, slug, kills, item_seconds, source_fetched_at FROM (
                SELECT c.name, c.slug, s.kills, s.time_in_seconds AS item_seconds,
                    s.source_fetched_at, s.vehicle_id AS item_id,
                    ROW_NUMBER() OVER (PARTITION BY c.name ORDER BY s.kills DESC, s.vehicle_id) AS rn
                FROM public.soldier_vehicle_stats AS s
                JOIN public.vehicle_catalog AS c ON c.vehicle_id=s.vehicle_id
                WHERE s.soldier_id=%s AND s.kills>0
            ) AS ranked WHERE rn=1 ORDER BY kills DESC, item_id LIMIT 9"""
    with psycopg.connect(dsn, connect_timeout=4,
                         options='-c default_transaction_read_only=on -c statement_timeout=4000') as conn:
        with conn.cursor() as cur:
            cur.execute(query, (soldier_id,))
            return cur.fetchall()
