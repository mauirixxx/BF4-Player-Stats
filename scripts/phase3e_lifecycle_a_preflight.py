#!/usr/bin/env python3
"""Read-only arm preflight for Phase 3E Lifecycle A."""
import os, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import bindparam, create_engine, text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *

def main()->int:
 url=os.environ.get('BF4PS_DATABASE_URL'); parsed=urlsplit(url or '')
 if not url or parsed.hostname!=EXPECTED_DB_HOST or parsed.path.lstrip('/')!=EXPECTED_DATABASE: print('REFUSING: wrong database target'); return 2
 engine=create_engine(url,pool_pre_ping=True); ids=list(COHORT_SOLDIER_IDS)
 q=text("""SELECT s.soldier_id,s.platform,cs.detailed_state,cs.detailed_last_attempt_at,cs.detailed_last_success_at,d.soldier_id current_id,cj.job_id FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id LEFT JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed' WHERE s.soldier_id IN :ids""").bindparams(bindparam('ids',expanding=True))
 with engine.connect() as c:
  assert_target(c); rows=c.execute(q,{'ids':ids}).mappings().all()
  collectors=c.execute(text("SELECT collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained,retired_at,current_job_id FROM collectors WHERE collector_uuid=ANY(:uuids)"),{'uuids':list(FROZEN_UUIDS)}).mappings().all()
  foreign=c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id<>ALL(:ids)"),{'ids':ids}).scalar_one()
 byuuid={r['collector_uuid']:r for r in collectors}; counts=Counter(str(r['platform']) for r in rows)
 pristine=all(r['detailed_state']=='never_attempted' and r['detailed_last_attempt_at'] is None and r['detailed_last_success_at'] is None and r['current_id'] is None and r['job_id'] is None for r in rows)
 identity=all((h.collector_uuid in byuuid and byuuid[h.collector_uuid]['collector_name']==h.collector_name and byuuid[h.collector_uuid]['hostname']==host and byuuid[h.collector_uuid]['lane']=='background' and byuuid[h.collector_uuid]['egress_key']==h.egress_key) for host,h in HOSTS.items())
 controls=all(bool(r['enabled']) and not bool(r['drained']) and r['retired_at'] is None and r['current_job_id'] is None for r in collectors)
 checks={'exact frozen 360 present':len(rows)==360 and len({r['soldier_id'] for r in rows})==360,'exact 120/120/120':counts==Counter({p:120 for p in PLATFORMS}),'cohort pristine':pristine,'three stable identities exact':identity and len(collectors)==3,'collectors enabled/undrained/idle':controls,'no foreign detailed/background queue':int(foreign)==0}
 print('===== BF4PS PHASE 3E LIFECYCLE A PREFLIGHT =====')
 for k,v in checks.items(): print(f'{k:<42} {"PASS" if v else "FAIL"}')
 print('database writes:                           0\nexternal Battlelog requests:               0')
 ok=all(checks.values()); print(f'\nLIFECYCLE A PREFLIGHT: {"PASS" if ok else "FAIL"}'); return 0 if ok else 1
if __name__=='__main__': sys.exit(main())
