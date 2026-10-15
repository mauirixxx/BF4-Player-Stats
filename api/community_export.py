#!/usr/bin/env python3
"""Read-only community snapshot builder. No collector writes; no database schema changes."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text

OUT = Path(os.environ.get('BF4PS_COMMUNITY_OUTPUT', '/var/www/bf4playerstats.com/community-stats.json'))
METRICS = ('kills','deaths','wins','losses','shots_fired','shots_hit','headshots',
           'revives','repairs','heals','resupplies','kill_assists','time_played_seconds',
           'total_score','vehicles_destroyed','flags_captured','flags_defended',
           'dogtags_taken','avenger_kills','savior_kills','nemesis_kills')
SQL = """
SELECT s.platform, count(*) AS detailed_soldiers,
""" + ",\n".join(f"coalesce(sum(d.{field}),0)::text AS {field}" for field in METRICS) + """
FROM public.detailed_stats_current d
JOIN public.soldiers s ON s.soldier_id=d.soldier_id
GROUP BY s.platform
"""

def build(connection):
    if connection.execute(text('select current_database()')).scalar_one() != 'bf4_playerstats':
        raise RuntimeError('Unexpected database')
    counts = {r.platform: int(r.count) for r in connection.execute(text(
        'SELECT platform,count(*) AS count FROM public.soldiers GROUP BY platform')).mappings()}
    values = {}
    for r in connection.execute(text(SQL)).mappings():
        values[r['platform']] = {key:int(r[key]) for key in ('detailed_soldiers',*METRICS)}
    platforms={}
    for platform in ('pc','ps4','xboxone'):
        platforms[platform]={'indexed_soldiers':counts.get(platform,0),
                             **values.get(platform,{'detailed_soldiers':0,**{m:0 for m in METRICS}})}
    all_values={key:sum(p[key] for p in platforms.values()) for key in platforms['pc']}
    return {'generated_at':datetime.now(timezone.utc).isoformat(),
            'source':'latest detailed_stats_current per soldier',
            'platforms':{'all':all_values,**platforms}}

def main():
    engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
    with engine.connect() as c:
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL statement_timeout = '25000ms'"))
        payload=build(c)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.community-',suffix='.json',dir=OUT.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(payload,f,separators=(',',':'))
            f.write('\n')
        os.chmod(tmp,0o644)
        os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('Published',payload['generated_at'],payload['platforms']['all']['detailed_soldiers'])

if __name__=='__main__':
    main()
