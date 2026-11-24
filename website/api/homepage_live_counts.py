#!/usr/bin/env python3
"""Fast exact homepage soldier counters, independent of heavy equipment totals."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text

OUT=Path('/var/www/bf4playerstats.com/homepage-live-counts.json')
engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
with engine.connect() as conn:
    if conn.execute(text('SELECT current_database()')).scalar_one()!='bf4_playerstats':
        raise RuntimeError('Unexpected database')
    soldiers=conn.execute(text('''SELECT count(*) FROM soldiers s
      WHERE NOT EXISTS (SELECT 1 FROM player_exclusions e
      WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)''')).scalar_one()
    full=conn.execute(text('''SELECT count(*) FROM collection_state cs
      JOIN soldiers s ON s.soldier_id=cs.soldier_id
      WHERE cs.detailed_state='success' AND cs.weapons_state='success'
        AND cs.vehicles_state='success' AND cs.profile_state='success'
        AND NOT EXISTS (SELECT 1 FROM player_exclusions e
          WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)''')).scalar_one()
    payload={'updated':datetime.now(timezone.utc).isoformat(), 'soldiers':soldiers,'full_soldiers':full}
    tmp=OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload,separators=(',',':')))
    os.chmod(tmp,0o644)
    os.replace(tmp,OUT)
