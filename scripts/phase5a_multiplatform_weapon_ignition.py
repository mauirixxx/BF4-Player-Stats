#!/usr/bin/env python3
"""Zero-request ignition preflight for the frozen Phase 5A weapon cohort."""
from __future__ import annotations

from collections import Counter
from sqlalchemy import bindparam, text

from bf4ps.db import make_engine
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT

EXPECTED_DATABASE = 'bf4_playerstats_test'
EXPECTED_REVISION = '0003_request_gates'
KNOWN_HISTORICAL_JOB_ID = 2209


def check(label: str, condition: bool, detail: str = '') -> None:
    status = 'PASS' if condition else 'FAIL'
    suffix = f'  {detail}' if detail else ''
    print(f'{label:<76} {status}{suffix}')
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")


def main() -> int:
    print('===== BF4PS PHASE 5A FROZEN COHORT IGNITION PREFLIGHT =====')
    print('scope: exact frozen 10 PC + 10 PS4 + 10 Xbox One weapon cohort')
    print('database writes: 0')
    print('Battlelog requests: 0')

    expected = {int(row[0]): row for row in FROZEN_COHORT}
    soldier_ids = list(expected)
    check('frozen artifact contains exactly 30 soldiers', len(FROZEN_COHORT) == 30)
    check('frozen soldier IDs are unique', len(soldier_ids) == len(set(soldier_ids)))
    check('frozen platform split is exactly 10/10/10', Counter(r[3] for r in FROZEN_COHORT) == Counter({'pc': 10, 'ps4': 10, 'xboxone': 10}))

    engine = make_engine()
    ids = bindparam('soldier_ids', expanding=True)
    with engine.connect() as conn:
        db = conn.execute(text('SELECT current_database()')).scalar_one()
        revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        recovery = bool(conn.execute(text('SELECT pg_is_in_recovery()')).scalar_one())
        read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
        check('target database is bf4_playerstats_test', db == EXPECTED_DATABASE, str(db))
        check('target is writable primary', not recovery and read_only == 'off', f'recovery={recovery} read_only={read_only}')
        check('Alembic revision is frozen Phase 5A revision', revision == EXPECTED_REVISION, str(revision))

        soldiers_stmt = text('''
            SELECT s.soldier_id, s.persona_id, s.current_name, s.platform,
                   cs.detailed_state, cs.weapons_state, cs.vehicles_state
            FROM soldiers s
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE s.soldier_id IN :soldier_ids
            ORDER BY s.soldier_id
        ''').bindparams(ids)
        rows = conn.execute(soldiers_stmt, {'soldier_ids': soldier_ids}).mappings().all()
        check('all 30 frozen soldiers still exist', len(rows) == 30, str(len(rows)))
        actual = {int(r['soldier_id']): r for r in rows}
        for soldier_id, frozen in expected.items():
            row = actual[soldier_id]
            identity = (soldier_id, int(row['persona_id']), str(row['current_name']), str(row['platform']))
            check(f'soldier {soldier_id} identity unchanged', identity == frozen, f'actual={identity!r} frozen={frozen!r}')
            check(f'soldier {soldier_id} detailed state is success', row['detailed_state'] == 'success', str(row['detailed_state']))
            check(f'soldier {soldier_id} weapons remain pristine', row['weapons_state'] == 'never_attempted', str(row['weapons_state']))
            check(f'soldier {soldier_id} vehicles remain pristine', row['vehicles_state'] == 'never_attempted', str(row['vehicles_state']))

        count_templates = {
            'frozen cohort has no weapon rows': 'SELECT count(*) FROM soldier_weapon_stats WHERE soldier_id IN :soldier_ids',
            'frozen cohort has no vehicle rows': 'SELECT count(*) FROM soldier_vehicle_stats WHERE soldier_id IN :soldier_ids',
            'frozen cohort has no weapon/vehicle jobs': "SELECT count(*) FROM collection_jobs WHERE soldier_id IN :soldier_ids AND resource IN ('weapons','vehicles')",
            'frozen cohort has no weapon/vehicle events': "SELECT count(*) FROM collection_events WHERE soldier_id IN :soldier_ids AND resource IN ('weapons','vehicles')",
        }
        for label, sql in count_templates.items():
            stmt = text(sql).bindparams(bindparam('soldier_ids', expanding=True))
            count = int(conn.execute(stmt, {'soldier_ids': soldier_ids}).scalar_one())
            check(label, count == 0, str(count))

        foreign = conn.execute(text('''
            SELECT job_id, soldier_id, resource, reason, status, attempt_count,
                   collector_uuid, lease_token, started_at, lease_expires_at,
                   last_error_class
            FROM collection_jobs
            WHERE resource IN ('weapons','vehicles')
              AND soldier_id NOT IN :soldier_ids
            ORDER BY job_id
        ''').bindparams(bindparam('soldier_ids', expanding=True)), {'soldier_ids': soldier_ids}).mappings().all()
        check('only known historical foreign full-stats job remains', len(foreign) == 1 and int(foreign[0]['job_id']) == KNOWN_HISTORICAL_JOB_ID, str([dict(r) for r in foreign]))
        hist = foreign[0]
        check('historical job 2209 remains pending and unowned', hist['status'] == 'pending' and hist['collector_uuid'] is None and hist['lease_token'] is None and hist['started_at'] is None, str(dict(hist)))
        check('historical job 2209 remains the failed single-live weapon probe', hist['resource'] == 'weapons' and hist['reason'] == 'phase5a_single_live_probe' and int(hist['attempt_count']) == 1 and hist['last_error_class'] == 'battlelog_normalization', str(dict(hist)))

    print('\n===== FROZEN COHORT =====')
    for platform in ('pc', 'ps4', 'xboxone'):
        print(f'\n[{platform}]')
        n = 0
        for soldier_id, persona_id, current_name, row_platform in FROZEN_COHORT:
            if row_platform != platform:
                continue
            n += 1
            print(f"{n:02d}. soldier={soldier_id} persona={persona_id} name={current_name!r} platform={row_platform}")

    print('\n===== ACCEPTANCE =====')
    print('database writes: 0')
    print('Battlelog requests: 0')
    print('PHASE 5A FROZEN COHORT IGNITION PREFLIGHT: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
