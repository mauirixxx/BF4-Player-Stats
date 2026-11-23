"""Read-only provider status for a BF4PS soldier; unknown is never clean."""
from sqlalchemy import text

SQL = text('''
SELECT s.platform, b.ba_banned, b.bf4db_banned,
       b.ba_checked_at, b.bf4db_checked_at, b.ba_reason, b.bf4db_reason
FROM public.soldiers s
LEFT JOIN public.soldier_ban_status b ON b.soldier_id = s.soldier_id
WHERE s.soldier_id = :soldier_id
  AND NOT EXISTS (
    SELECT 1 FROM public.player_exclusions e
    WHERE e.platform = s.platform AND e.persona_id = s.persona_id AND e.active
  )
''')

def get_status(conn, soldier_id):
    row = conn.execute(SQL, {'soldier_id': soldier_id}).mappings().first()
    if row is None:
        return None
    def status(value):
        return 'unknown' if value is None else ('banned' if value else 'clean')
    if row['platform'] != 'pc':
        return {'agency': 'unknown', 'bf4db': 'unknown'}
    return {'agency': status(row['ba_banned']), 'bf4db': status(row['bf4db_banned']),
            'ba_checked_at': row['ba_checked_at'], 'bf4db_checked_at': row['bf4db_checked_at'],
            'ba_reason': row['ba_reason'], 'bf4db_reason': row['bf4db_reason']}
