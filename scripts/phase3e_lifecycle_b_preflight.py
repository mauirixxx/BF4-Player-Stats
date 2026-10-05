#!/usr/bin/env python3
"""Read-only arm preflight for Phase 3E Lifecycle B."""
from sqlalchemy import create_engine, text
from phase3e_lifecycle_b_common import *

def main()->int:
    e=create_engine(database_url(),pool_pre_ping=True)
    checks=[]
    with e.connect() as c:
        assert_target(c); checks.append(("expected test primary and Alembic head",True))
        foreign=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource=:r AND lane=:l AND status IN ('claimed','running')"),{'r':RESOURCE,'l':LANE}).scalar_one())
        checks.append(("no detailed/background job currently owned",foreign==0))
        rows=c.execute(text("SELECT collector_uuid,collector_name,hostname,enabled,drained,current_job_id FROM collectors WHERE collector_uuid IN (:v,:r) ORDER BY hostname"),{'v':VICTIM_UUID,'r':RECLAIMER_UUID}).mappings().all()
        exact=len(rows)==2 and {str(x['collector_uuid']) for x in rows}=={str(VICTIM_UUID),str(RECLAIMER_UUID)}
        checks.append(("victim and reclaimer stable identities present",exact))
        eligible=exact and all(x['enabled'] and not x['drained'] and x['current_job_id'] is None for x in rows)
        checks.append(("victim/reclaimer enabled undrained idle",eligible))
        candidate=c.execute(text("""
            SELECT s.soldier_id,s.persona_id,s.platform,s.current_name
            FROM soldiers s
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource=:r
            WHERE s.platform='pc' AND cj.job_id IS NULL
              AND cs.detailed_state='never'
              AND cs.detailed_last_attempt_at IS NULL
              AND cs.detailed_last_success_at IS NULL
              AND cs.detailed_last_error IS NULL
            ORDER BY s.soldier_id
            LIMIT 1
        """),{'r':RESOURCE}).mappings().one_or_none()
        checks.append(("one pristine PC candidate available",candidate is not None))
    print("===== BF4PS PHASE 3E LIFECYCLE B PREFLIGHT =====")
    if candidate: print(f"candidate soldier={candidate['soldier_id']} persona={candidate['persona_id']} name={candidate['current_name']!r} platform={candidate['platform']}")
    for label,ok in checks: print(f"{label:<48} {'PASS' if ok else 'FAIL'}")
    print("database writes: 0\nBattlelog requests: 0")
    ok=all(v for _,v in checks)
    print(f"LIFECYCLE B PREFLIGHT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1

if __name__=='__main__': raise SystemExit(main())
