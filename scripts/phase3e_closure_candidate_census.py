#!/usr/bin/env python3
"""Read-only census explaining Phase 3E closure candidate availability.

No queue mutation and no external requests. This intentionally reports aggregate
eligibility stages plus a small sample of the safest reusable PC soldiers so the
closure cohort can be chosen from observed database state rather than assumptions.
"""
from __future__ import annotations
from sqlalchemy import create_engine,text,bindparam
from phase3e_lifecycle_b_common import database_url,assert_target

EXCLUDE_IDS=tuple(range(269,389))+tuple(range(928,1147))+tuple(range(8635,8702))+(389,)


def scalar(c,sql,params=None):
    return c.execute(text(sql).bindparams(bindparam('exclude_ids',expanding=True)) if ':exclude_ids' in sql else text(sql),params or {}).scalar_one()


def main()->int:
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.connect() as c:
        assert_target(c)
        params={'exclude_ids':list(EXCLUDE_IDS)}
        counts={
            'all PC soldiers': scalar(c,"SELECT count(*) FROM soldiers WHERE platform='pc'"),
            'PC outside Lifecycle A/B': scalar(c,"SELECT count(*) FROM soldiers WHERE platform='pc' AND soldier_id NOT IN :exclude_ids",params),
            'outside cohort with collection_state': scalar(c,"""SELECT count(*) FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids""",params),
            'outside cohort without detailed job': scalar(c,"""SELECT count(*) FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed'
                WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cj.job_id IS NULL""",params),
            'outside cohort detailed_state=never': scalar(c,"""SELECT count(*) FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cs.detailed_state='never'""",params),
            'outside cohort never + no detailed job': scalar(c,"""SELECT count(*) FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed'
                WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cs.detailed_state='never' AND cj.job_id IS NULL""",params),
            'strict pristine candidates': scalar(c,"""SELECT count(*) FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed'
                WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cj.job_id IS NULL
                  AND cs.detailed_state='never' AND cs.detailed_last_attempt_at IS NULL
                  AND cs.detailed_last_success_at IS NULL AND cs.detailed_last_error_class IS NULL
                  AND cs.detailed_last_error_message IS NULL""",params),
            'successful reusable, no detailed job': scalar(c,"""SELECT count(*) FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
                LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed'
                WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cj.job_id IS NULL
                  AND cs.detailed_state='success' AND cs.detailed_last_success_at IS NOT NULL""",params),
        }
        states=c.execute(text("""SELECT cs.detailed_state,count(*) AS n
            FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids
            GROUP BY cs.detailed_state ORDER BY cs.detailed_state""").bindparams(bindparam('exclude_ids',expanding=True)),params).all()
        job_states=c.execute(text("""SELECT cj.status,count(*) AS n
            FROM soldiers s JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id
            WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cj.resource='detailed'
            GROUP BY cj.status ORDER BY cj.status""").bindparams(bindparam('exclude_ids',expanding=True)),params).all()
        reusable=c.execute(text("""SELECT s.soldier_id,s.persona_id,s.current_name,cs.detailed_last_success_at,d.source_fetched_at
            FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
            LEFT JOIN collection_jobs cj ON cj.soldier_id=s.soldier_id AND cj.resource='detailed'
            WHERE s.platform='pc' AND s.soldier_id NOT IN :exclude_ids AND cj.job_id IS NULL
              AND cs.detailed_state='success' AND cs.detailed_last_success_at IS NOT NULL
            ORDER BY cs.detailed_last_success_at,s.soldier_id LIMIT 10""").bindparams(bindparam('exclude_ids',expanding=True)),params).mappings().all()
    print('===== BF4PS PHASE 3E CLOSURE CANDIDATE CENSUS =====')
    print('\nEligibility stages:')
    for label,n in counts.items(): print(f'{label:<42} {n}')
    print('\nDetailed state outside Lifecycle A/B:')
    if states:
        for state,n in states: print(f'{state:<20} {n}')
    else: print('(none)')
    print('\nExisting detailed-job status outside Lifecycle A/B:')
    if job_states:
        for status,n in job_states: print(f'{status:<20} {n}')
    else: print('(none)')
    print('\nSafest reusable-success sample (diagnostic only; NOT YET AUTHORIZED):')
    if reusable:
        for r in reusable: print(f"soldier={r['soldier_id']} persona={r['persona_id']} name={r['current_name']!r} last_success={r['detailed_last_success_at']} source={r['source_fetched_at']}")
    else: print('(none)')
    print('\ndatabase writes: 0')
    print('Battlelog requests: 0')
    print('CENSUS: COMPLETE')
    return 0
if __name__=='__main__': raise SystemExit(main())
