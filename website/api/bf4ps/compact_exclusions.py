"""Stable fingerprint of active moderation exclusions in one DB snapshot.

Used for format-2 publication and reads. Never rely on updated_at timestamps:
manual writes, deactivation and backdating must all invalidate snapshots.
"""
import hashlib
from sqlalchemy import text


def exclusion_fingerprint(conn):
    digest = hashlib.sha256()
    rows = conn.execute(text('''SELECT platform,persona_id FROM player_exclusions
      WHERE active ORDER BY platform,persona_id'''))
    for platform, persona_id in rows:
        digest.update(f'{platform}:{int(persona_id)}\n'.encode('ascii'))
    return digest.hexdigest()
