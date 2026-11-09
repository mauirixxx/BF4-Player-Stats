"""Independent, checkpointed BF4BR -> BF4PS identity and alias import.

Never uses report timestamps as name observation timestamps. Never changes
existing BF4PS current names. Requires a BF4BR read-only database account.
"""
import logging
import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from bf4ps.config import database_url

LOG = logging.getLogger(__name__)
PLATFORMS = {1: 'pc', 32: 'ps4', 64: 'xboxone'}
BATCH = 100


def checkpoint(conn, name):
    conn.execute(text("INSERT INTO discovery_state(source_name,last_alias_id) VALUES (:name,0) ON CONFLICT(source_name) DO NOTHING"), {'name':name})
    return conn.execute(text('SELECT last_alias_id FROM discovery_state WHERE source_name=:name FOR UPDATE'), {'name':name}).scalar_one()


def sync_identities(source, dest):
    new_count = duplicate_count = excluded_count = invalid_count = 0
    with dest.begin() as dst:
        last = checkpoint(dst, 'bf4br_identities')
        rows = source.execute(text('SELECT id,platform,persona_id,current_name,current_name_observed_at FROM players WHERE id>:last ORDER BY id LIMIT :limit'), {'last':last,'limit':BATCH}).mappings().all()
        for r in rows:
            platform = PLATFORMS.get(r['platform'])
            if not platform or not r['persona_id'] or not r['current_name'] or not r['current_name'].strip():
                invalid_count += 1
                continue
            if dst.execute(text('SELECT 1 FROM player_exclusions WHERE platform=:platform AND persona_id=:persona AND active'), {'platform':platform,'persona':r['persona_id']}).scalar():
                excluded_count += 1
                continue
            stamp = r['current_name_observed_at']
            # Savepoints keep one rejected identity from stopping a whole batch.
            with dst.begin_nested():
                sid = dst.execute(text('''INSERT INTO soldiers(persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,:platform,:name,:stamp,:stamp)
                    ON CONFLICT(persona_id,platform) DO NOTHING RETURNING soldier_id'''), {'persona':r['persona_id'],'platform':platform,'name':r['current_name'],'stamp':stamp}).scalar_one_or_none()
                if sid is None:
                    duplicate_count += 1
                    sid = dst.execute(text('SELECT soldier_id FROM soldiers WHERE persona_id=:persona AND platform=:platform'), {'persona':r['persona_id'],'platform':platform}).scalar_one()
                else:
                    new_count += 1
                dst.execute(text('''INSERT INTO soldier_names(soldier_id,name,first_seen_at,last_seen_at)
                    VALUES (:sid,:name,:stamp,:stamp) ON CONFLICT(soldier_id,name) DO UPDATE
                    SET first_seen_at=LEAST(soldier_names.first_seen_at,EXCLUDED.first_seen_at),
                        last_seen_at=GREATEST(soldier_names.last_seen_at,EXCLUDED.last_seen_at)'''), {'sid':sid,'name':r['current_name'],'stamp':stamp})
                dst.execute(text('INSERT INTO collection_state(soldier_id) VALUES (:sid) ON CONFLICT(soldier_id) DO NOTHING'), {'sid':sid})
        if rows:
            dst.execute(text('UPDATE discovery_state SET last_alias_id=:last,last_success_at=now(),updated_at=now() WHERE source_name=:name'), {'last':rows[-1]['id'],'name':'bf4br_identities'})
        LOG.info('BF4BR identity batch committed: scanned=%d new=%d duplicates=%d excluded=%d invalid=%d', len(rows), new_count, duplicate_count, excluded_count, invalid_count)
        return len(rows)


def sync_names(source, dest):
    with dest.begin() as dst:
        last = checkpoint(dst, 'bf4br_names')
        rows = source.execute(text('''SELECT h.id,p.platform,p.persona_id,h.player_name,h.observed_at
            FROM player_name_history h JOIN players p ON p.id=h.player_id
            WHERE h.id>:last ORDER BY h.id LIMIT :limit'''), {'last':last,'limit':BATCH}).mappings().all()
        for r in rows:
            platform = PLATFORMS.get(r['platform'])
            if not platform or not r['player_name'] or not r['player_name'].strip():
                continue
            if dst.execute(text('SELECT 1 FROM player_exclusions WHERE platform=:platform AND persona_id=:persona AND active'), {'platform':platform,'persona':r['persona_id']}).scalar():
                continue
            sid = dst.execute(text('SELECT soldier_id FROM soldiers WHERE platform=:platform AND persona_id=:persona'), {'platform':platform,'persona':r['persona_id']}).scalar_one_or_none()
            if sid is None:
                # Identity stream may not yet have reached this player; retry on next run.
                break
            dst.execute(text('''INSERT INTO soldier_names(soldier_id,name,first_seen_at,last_seen_at)
                VALUES (:sid,:name,:stamp,:stamp) ON CONFLICT(soldier_id,name) DO UPDATE
                SET first_seen_at=LEAST(soldier_names.first_seen_at,EXCLUDED.first_seen_at),
                    last_seen_at=GREATEST(soldier_names.last_seen_at,EXCLUDED.last_seen_at)'''), {'sid':sid,'name':r['player_name'],'stamp':r['observed_at']})
        else:
            if rows:
                dst.execute(text('UPDATE discovery_state SET last_alias_id=:last,last_success_at=now(),updated_at=now() WHERE source_name=:name'), {'last':rows[-1]['id'],'name':'bf4br_names'})
            return len(rows)
        return 0


def retry_deadlocks(func, source, dest, attempts=6):
    """Retry only PostgreSQL deadlocks; transactions and cursors roll back together."""
    for attempt in range(attempts):
        try:
            return func(source, dest)
        except DBAPIError as exc:
            if getattr(exc.orig, 'sqlstate', None) != '40P01' or attempt == attempts - 1:
                raise
            delay = min(0.25 * (2 ** attempt), 5.0)
            LOG.warning('BF4BR sync deadlock; retry %d/%d after %.2fs', attempt + 1, attempts - 1, delay)
            time.sleep(delay)


def main():
    logging.basicConfig(level=logging.INFO)
    url = os.environ['BF4PS_BF4BR_DATABASE_URL']
    with create_engine(url, pool_pre_ping=True).connect() as source:
        engine = create_engine(database_url(),pool_pre_ping=True)
        try:
            for stream,func in [('identities',sync_identities),('names',sync_names)]:
                total=0
                while True:
                    n=retry_deadlocks(func,source,engine)
                    total+=n
                    if n<BATCH: break
                    if total>=10000: break
                LOG.info('BF4BR %s processed=%d',stream,total)
        finally: engine.dispose()

if __name__=='__main__': main()

[executed on device: tcou (720a0073-649a-4660-8c09-00c2e6d0e587)]