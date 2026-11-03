#!/usr/bin/env python3
"""Lightweight homepage counter export, independent of full dossier snapshot."""
import json, os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text

OUT=Path('/var/www/bf4playerstats.com/homepage-summary.json')
engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
with engine.connect() as c:
    if c.execute(text('select current_database()')).scalar_one()!='bf4_playerstats':
        raise RuntimeError('Unexpected database')
    result=c.execute(text('''
      SELECT
      (SELECT count(*) FROM soldiers s WHERE NOT EXISTS (SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) soldiers,
      (SELECT count(*) FROM soldier_weapon_stats w JOIN soldiers s ON s.soldier_id=w.soldier_id WHERE NOT EXISTS (SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) weapons,
      (SELECT count(*) FROM soldier_vehicle_stats v JOIN soldiers s ON s.soldier_id=v.soldier_id WHERE NOT EXISTS (SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) vehicles,
      (SELECT count(*) FROM profile_soldiers) profiles,
      (SELECT count(*) FROM platoons WHERE last_success_at IS NOT NULL) platoons
    ''')).mappings().one()
    states=c.execute(text('''
      SELECT count(*) FILTER (WHERE cs.detailed_state='success') detailed,
      count(*) FILTER (WHERE cs.detailed_state='success' AND cs.weapons_state='success' AND cs.vehicles_state='success' AND cs.profile_state='success') full
      FROM collection_state cs JOIN soldiers s ON s.soldier_id=cs.soldier_id
      WHERE NOT EXISTS (SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
    ''')).mappings().one()
    payload={'updated':datetime.now(timezone.utc).isoformat(),'summary':dict(result),'detailed_soldiers':states['detailed'],'full_soldiers':states['full']}
    tmp=OUT.with_suffix('.json.tmp');tmp.write_text(json.dumps(payload,separators=(',',':')));os.chmod(tmp,0o644);os.replace(tmp,OUT)
