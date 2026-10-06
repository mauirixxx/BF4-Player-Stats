#!/usr/bin/env python3
"""Resume/complete jobs 815/816 on kah-01 while victim job 814 remains abandoned."""
from __future__ import annotations

import socket
from sqlalchemy import create_engine, text

from bf4ps.collector_runtime import heartbeat_collector
from bf4ps.detailed_collector import CollectorIdentity, CollectedJob, FailedJob, collect_one_detailed_job
from phase3e_closure_survivor_cohort import SURVIVOR_SOLDIER_IDS, VICTIM_SOLDIER_ID
from phase3e_lifecycle_b_common import RECLAIMER_HOST, RECLAIMER_UUID, assert_target, database_url

VICTIM_JOB_ID = 814
SURVIVOR_JOB_IDS = (815, 816)
EXPECTED = dict(zip(SURVIVOR_JOB_IDS, SURVIVOR_SOLDIER_IDS))


def _event_ok(row) -> bool:
    return (
        row['event_type'] == 'collection_success'
        and int(row['attempt_number']) == 1
        and row['result'] == 'success'
        and row['collector_uuid'] == RECLAIMER_UUID
    )


def main() -> int:
    host = socket.gethostname().split('.')[0]
    if host != RECLAIMER_HOST:
        raise SystemExit(f"REFUSING: survivor worker must run on {RECLAIMER_HOST}, got {host}")

    engine = create_engine(database_url(), pool_pre_ping=True)
    with engine.begin() as conn:
        assert_target(conn)
        control = heartbeat_collector(
            conn,
            collector_uuid=RECLAIMER_UUID,
            software_version='phase3e-closure-survivor-worker-resume',
        )
        if not control.may_claim:
            raise RuntimeError('survivor collector is disabled or drained')

        victim = conn.execute(text("""
            SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
                   claimed_at,started_at,lease_expires_at
            FROM collection_jobs WHERE job_id=:job_id
        """), {'job_id': VICTIM_JOB_ID}).mappings().one_or_none()
        if victim is None:
            raise RuntimeError('victim job 814 is missing before survivor progress')
        if (
            int(victim['soldier_id']) != VICTIM_SOLDIER_ID
            or victim['status'] != 'running'
            or int(victim['attempt_count']) != 1
            or victim['collector_uuid'] is None
            or victim['lease_token'] is None
            or victim['claimed_at'] is None
            or victim['started_at'] is None
            or victim['lease_expires_at'] is None
        ):
            raise RuntimeError(f'unexpected abandoned victim shape: {dict(victim)}')

        jobs = conn.execute(text("""
            SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
                   claimed_at,started_at,lease_expires_at
            FROM collection_jobs
            WHERE job_id = ANY(:job_ids)
            ORDER BY job_id
        """), {'job_ids': list(SURVIVOR_JOB_IDS)}).mappings().all()
        jobs_by_id = {int(row['job_id']): row for row in jobs}

        events = conn.execute(text("""
            SELECT event_id,job_id,soldier_id,event_type,attempt_number,result,http_status,collector_uuid
            FROM collection_events
            WHERE job_id = ANY(:job_ids)
            ORDER BY event_id
        """), {'job_ids': list(SURVIVOR_JOB_IDS)}).mappings().all()
        events_by_job = {}
        for event in events:
            events_by_job.setdefault(int(event['job_id']), []).append(event)

        completed_ids = []
        pending_ids = []
        for job_id, soldier_id in EXPECTED.items():
            job_events = events_by_job.get(job_id, [])
            row = jobs_by_id.get(job_id)
            if row is None:
                if len(job_events) != 1 or int(job_events[0]['soldier_id']) != soldier_id or not _event_ok(job_events[0]):
                    raise RuntimeError(f'finalized survivor {job_id} lacks exact success evidence: {job_events}')
                completed_ids.append(job_id)
                continue

            if int(row['soldier_id']) != soldier_id:
                raise RuntimeError(f'survivor identity drift: {dict(row)}')
            if job_events:
                raise RuntimeError(f'survivor {job_id} has both live queue row and terminal events: {job_events}')
            if row['status'] != 'pending' or int(row['attempt_count']) != 0:
                raise RuntimeError(f'survivor job not pristine pending: {dict(row)}')
            if any(row[k] is not None for k in (
                'collector_uuid','lease_token','claimed_at','started_at','lease_expires_at'
            )):
                raise RuntimeError(f'survivor job unexpectedly owned: {dict(row)}')
            pending_ids.append(job_id)

        if not completed_ids and not pending_ids:
            raise RuntimeError('no survivor state found')

        identity = conn.execute(text("""
            SELECT collector_name,hostname,egress_key,lane
            FROM collectors WHERE collector_uuid=:collector_uuid
        """), {'collector_uuid': RECLAIMER_UUID}).mappings().one()

    collector_identity = CollectorIdentity(
        collector_uuid=RECLAIMER_UUID,
        collector_name=identity['collector_name'],
        hostname=identity['hostname'],
        egress_key=identity['egress_key'],
        lane=identity['lane'],
    )

    print('===== BF4PS PHASE 3E SURVIVOR-PROGRESS RESUME =====', flush=True)
    print(f'host: {host}', flush=True)
    print(f'victim job: {VICTIM_JOB_ID} remains abandoned attempt=1', flush=True)
    print(f'already completed survivor jobs: {tuple(completed_ids)}', flush=True)
    print(f'pending survivor jobs: {tuple(pending_ids)}', flush=True)
    print(f'authorized Battlelog requests this run: at most {len(pending_ids)}', flush=True)

    for index, job_id in enumerate(pending_ids, start=1):
        soldier_id = EXPECTED[job_id]
        result = collect_one_detailed_job(
            engine,
            identity=collector_identity,
            request_interval_seconds=5.0,
            lease_seconds=120,
            timeout_seconds=15.0,
            retry_after_seconds=300,
            allowed_soldier_ids=(soldier_id,),
            max_total_attempts=1,
        )
        if result is None:
            raise RuntimeError(f'production collector returned no job for survivor {job_id}')
        if result.job_id != job_id or result.soldier_id != soldier_id:
            raise RuntimeError(f'foreign job collected: {result}')
        if isinstance(result, FailedJob):
            raise RuntimeError(
                f'survivor source failure job={result.job_id} soldier={result.soldier_id} '
                f'class={result.error_class} http={result.http_status}'
            )
        if not isinstance(result, CollectedJob):
            raise RuntimeError(f'unexpected collector result: {result}')
        print(
            f'[{index}/{len(pending_ids)}] SUCCESS job={result.job_id} soldier={result.soldier_id} '
            f'history_appended={result.history_appended}',
            flush=True,
        )

    with engine.begin() as conn:
        victim_after = conn.execute(text("""
            SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
                   claimed_at,started_at,lease_expires_at
            FROM collection_jobs WHERE job_id=:job_id
        """), {'job_id': VICTIM_JOB_ID}).mappings().one_or_none()
        remaining = conn.execute(text("""
            SELECT job_id FROM collection_jobs
            WHERE job_id = ANY(:job_ids)
            ORDER BY job_id
        """), {'job_ids': list(SURVIVOR_JOB_IDS)}).scalars().all()
        events = conn.execute(text("""
            SELECT event_id,job_id,soldier_id,event_type,attempt_number,result,http_status,collector_uuid
            FROM collection_events
            WHERE job_id = ANY(:job_ids)
            ORDER BY event_id
        """), {'job_ids': list(SURVIVOR_JOB_IDS)}).mappings().all()
        states = conn.execute(text("""
            SELECT soldier_id,detailed_state,detailed_last_success_at,detailed_last_error_class
            FROM collection_state
            WHERE soldier_id = ANY(:soldier_ids)
            ORDER BY soldier_id
        """), {'soldier_ids': list(SURVIVOR_SOLDIER_IDS)}).mappings().all()
        current_count = conn.execute(text("""
            SELECT count(*) FROM detailed_stats_current
            WHERE soldier_id = ANY(:soldier_ids)
        """), {'soldier_ids': list(SURVIVOR_SOLDIER_IDS)}).scalar_one()
        conn.execute(text("""
            UPDATE collectors SET current_job_id=NULL, updated_at=now()
            WHERE collector_uuid=:collector_uuid
              AND current_job_id = ANY(:job_ids)
        """), {'collector_uuid': RECLAIMER_UUID, 'job_ids': list(SURVIVOR_JOB_IDS)})

    if victim_after is None or dict(victim_after) != dict(victim):
        raise RuntimeError(
            f'victim job changed during survivor work: before={dict(victim)} '
            f'after={None if victim_after is None else dict(victim_after)}'
        )
    if remaining:
        raise RuntimeError(f'survivor jobs did not finalize: {remaining}')
    if len(events) != 2:
        raise RuntimeError(f'expected exactly two survivor terminal events, found {len(events)}')
    if {int(row['job_id']) for row in events} != set(SURVIVOR_JOB_IDS):
        raise RuntimeError(f'survivor event job set mismatch: {[dict(row) for row in events]}')
    for event in events:
        if int(event['soldier_id']) != EXPECTED[int(event['job_id'])] or not _event_ok(event):
            raise RuntimeError(f'unexpected survivor terminal event: {dict(event)}')
    if len(states) != 2 or any(
        row['detailed_state'] != 'success'
        or row['detailed_last_success_at'] is None
        or row['detailed_last_error_class'] is not None
        for row in states
    ):
        raise RuntimeError(f'survivor detailed state did not converge: {[dict(row) for row in states]}')
    if int(current_count) != 2:
        raise RuntimeError(f'expected two survivor detailed current rows, found {current_count}')

    print('victim job unchanged while survivors progressed: PASS')
    for event in events:
        print(
            f"terminal event: {event['event_id']} job={event['job_id']} "
            f"soldier={event['soldier_id']} attempt={event['attempt_number']} http={event['http_status']}"
        )
    print('survivor jobs finalized: PASS')
    print('survivor detailed state/current: PASS')
    print('SURVIVOR-PROGRESS RESUME: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
