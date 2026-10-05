#!/usr/bin/env python3
"""Arm hnl-01 as the intentionally abandoned victim for Phase 3E survivor-progress closure."""
from __future__ import annotations

import socket
import time

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import claim_next_job, mark_job_running
from bf4ps.collector_runtime import heartbeat_collector
from phase3e_closure_survivor_cohort import COHORT, SURVIVOR_SOLDIER_IDS, VICTIM_SOLDIER_ID
from phase3e_lifecycle_b_common import (
    LANE, LEASE_SECONDS, RESOURCE, VICTIM_HOST, VICTIM_UUID,
    assert_target, database_url,
)

EXPECTED_JOBS = {814: 390, 815: 391, 816: 392}


def main() -> int:
    host = socket.gethostname().split(".")[0]
    if host != VICTIM_HOST:
        raise SystemExit(f"REFUSING: victim must run on {VICTIM_HOST}, got {host}")

    soldier = next(row for row in COHORT if row[0] == VICTIM_SOLDIER_ID)
    _, persona_id, platform, current_name = soldier
    engine = create_engine(database_url(), pool_pre_ping=True)

    with engine.begin() as conn:
        assert_target(conn)
        control = heartbeat_collector(
            conn,
            collector_uuid=VICTIM_UUID,
            software_version="phase3e-closure-survivor-victim",
        )
        if not control.may_claim:
            raise RuntimeError("victim collector is disabled or drained")

        rows = conn.execute(text("""
            SELECT job_id, soldier_id, resource, lane, status, attempt_count,
                   collector_uuid, lease_token, claimed_at, started_at, lease_expires_at
            FROM collection_jobs
            WHERE job_id = ANY(:job_ids)
            ORDER BY job_id
            FOR UPDATE
        """), {"job_ids": list(EXPECTED_JOBS)}).mappings().all()

        if len(rows) != 3:
            raise RuntimeError(f"expected three closure jobs, found {len(rows)}")

        for row in rows:
            job_id = int(row["job_id"])
            if job_id not in EXPECTED_JOBS or int(row["soldier_id"]) != EXPECTED_JOBS[job_id]:
                raise RuntimeError(f"closure identity drift: {dict(row)}")
            if row["resource"] != RESOURCE or row["lane"] != LANE:
                raise RuntimeError(f"closure resource/lane drift: {dict(row)}")
            if row["status"] != "pending" or int(row["attempt_count"]) != 0:
                raise RuntimeError(f"closure job not pristine pending: {dict(row)}")
            if any(row[k] is not None for k in (
                "collector_uuid", "lease_token", "claimed_at", "started_at", "lease_expires_at"
            )):
                raise RuntimeError(f"closure job unexpectedly owned: {dict(row)}")

        job = claim_next_job(
            conn,
            collector_uuid=VICTIM_UUID,
            lane=LANE,
            resource=RESOURCE,
            lease_seconds=LEASE_SECONDS,
            allowed_soldier_ids=(VICTIM_SOLDIER_ID,),
            max_total_attempts=1,
        )
        if job is None or job.job_id != 814 or job.soldier_id != VICTIM_SOLDIER_ID:
            raise RuntimeError(f"victim did not claim exact job 814: {job}")
        if not mark_job_running(conn, job):
            raise RuntimeError("victim could not mark job 814 running")

        conn.execute(text("""
            UPDATE collectors
            SET current_job_id=:job_id, updated_at=now()
            WHERE collector_uuid=:collector_uuid
        """), {"job_id": job.job_id, "collector_uuid": VICTIM_UUID})

    with engine.connect() as conn:
        victim_row = conn.execute(text("""
            SELECT status, attempt_count, collector_uuid, lease_token,
                   claimed_at, started_at, lease_expires_at
            FROM collection_jobs WHERE job_id=814
        """)).mappings().one()
        survivors = conn.execute(text("""
            SELECT job_id, status, attempt_count, collector_uuid
            FROM collection_jobs
            WHERE job_id = ANY(:job_ids)
            ORDER BY job_id
        """), {"job_ids": [815, 816]}).mappings().all()
        now = conn.execute(text("SELECT now()")).scalar_one()

    if (
        victim_row["status"] != "running"
        or int(victim_row["attempt_count"]) != 1
        or victim_row["collector_uuid"] != VICTIM_UUID
        or victim_row["lease_token"] != job.lease_token
    ):
        raise RuntimeError("post-claim victim ownership verification failed")

    if len(survivors) != 2 or any(
        row["status"] != "pending"
        or int(row["attempt_count"]) != 0
        or row["collector_uuid"] is not None
        for row in survivors
    ):
        raise RuntimeError(f"survivor jobs changed before victim kill: {[dict(row) for row in survivors]}")

    print("===== BF4PS PHASE 3E SURVIVOR-PROGRESS VICTIM ARMED =====", flush=True)
    print(f"host:           {host}", flush=True)
    print(f"victim job:     {job.job_id}", flush=True)
    print(f"victim soldier: {VICTIM_SOLDIER_ID} {current_name!r} persona={persona_id} platform={platform}", flush=True)
    print(f"attempt:        {job.attempt_count}", flush=True)
    print(f"lease token:    {job.lease_token}", flush=True)
    print(f"claimed at:     {victim_row['claimed_at']}", flush=True)
    print(f"started at:     {victim_row['started_at']}", flush=True)
    print(f"lease expires:  {victim_row['lease_expires_at']}", flush=True)
    print(f"database now:   {now}", flush=True)
    print(f"survivor soldiers: {SURVIVOR_SOLDIER_IDS}", flush=True)
    print("survivor jobs: 815 and 816 remain pending", flush=True)
    print("Battlelog requests: 0", flush=True)
    print("lease renewal: NONE", flush=True)
    print("clean release: NONE", flush=True)
    print("", flush=True)
    print("=====================================================", flush=True)
    print("===== KILL HNL-01 COLLECTOR NOW (Ctrl-C / kill) =====", flush=True)
    print("=====================================================", flush=True)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
