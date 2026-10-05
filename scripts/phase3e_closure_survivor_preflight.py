#!/usr/bin/env python3
"""Read-only preflight for the Phase 3E abrupt-loss survivor-progress closure test."""
from __future__ import annotations
from sqlalchemy import create_engine,text,bindparam
from phase3e_lifecycle_a_common import HOSTS,FROZEN_UUIDS
from phase3e_lifecycle_b_common import database_url,assert_target

EXCLUDE_IDS=tuple(range(269,389))+tuple(range(928,1147))+tuple(range(8635,8702))+(389,)


def main()->int:
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.connect() as c:
        assert_target(c)
        collectors=c.execute(text("""SELECT collector_uuid,collector_name,hostname,egress_key,enabled,drained,current_job_id,retired_at
            FROM collectors WHERE collector_uuid IN :uuids ORDER BY hostname""").bindparams(bindparam('uuids',expanding=True)),{'uuids':list(FROZEN_UUIDS)}).mappings().all()
        foreign_owned=c.execute(text("""SELECT count(*) FROM collection_jobs
            WHERE resource='detailed' AND lane='background' AND status IN ('claimed','running')""")).scalar_one()
        candidates=c.execute(text("""SELECT s.soldier_id,s.persona_id,s.platform,s.current_name
            FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed'
            WHERE s.platform='pc' AND cj.job_id IS NULL
              AND s.soldier_id NOT IN :exclude_ids
              AND cs.detailed_state='never'
              AND cs.detailed_last_attempt_at IS NULL
              AND cs.detailed_last_success_at IS NULL
              AND cs.detailed_last_error_class IS NULL
              AND cs.detailed_last_error_message IS NULL
            ORDER BY s.soldier_id LIMIT 3""").bindparams(bindparam('exclude_ids',expanding=True)),{'exclude_ids':list(EXCLUDE_IDS)}).mappings().all()
    cmap={r['collector_uuid']:r for r in collectors}
    identity_ok=len(cmap)==3 and all(cmap[h.collector_uuid]['collector_name']==h.collector_name and cmap[h.collector_uuid]['hostname']==host and cmap[h.collector_uuid]['egress_key']==h.egress_key and cmap[h.collector_uuid]['retired_at'] is None for host,h in HOSTS.items())
    controls_ok=len(cmap)==3 and all(r['enabled'] and not r['drained'] and r['current_job_id'] is None for r in cmap.values())
    checks=[
        ('three stable collector identities exact',identity_ok),
        ('collectors enabled/undrained/idle',controls_ok),
        ('no detailed/background job currently owned',foreign_owned==0),
        ('three pristine fresh PC candidates available',len(candidates)==3),
    ]
    print('===== BF4PS PHASE 3E SURVIVOR-PROGRESS PREFLIGHT =====')
    for r in candidates: print(f"candidate soldier={r['soldier_id']} persona={r['persona_id']} name={r['current_name']!r} platform={r['platform']}")
    for label,ok in checks: print(f'{label:<48} {"PASS" if ok else "FAIL"}')
    print('database writes: 0')
    print('Battlelog requests: 0')
    ok=all(v for _,v in checks)
    print(f'SURVIVOR-PROGRESS PREFLIGHT: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
