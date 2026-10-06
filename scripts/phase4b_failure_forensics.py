#!/usr/bin/env python3
"""Read-only forensic report for Phase 4B terminal detailed failures."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import bindparam, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase4b_cohort import SOLDIER_IDS
from phase4b_common import EXPECTED_DATABASE, EXPECTED_DB_HOST, assert_target


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    engine = create_engine(url, pool_pre_ping=True)
    ids = list(SOLDIER_IDS)
    ids_param = bindparam("ids", expanding=True)

    with engine.connect() as conn:
        assert_target(conn)

        failures = conn.execute(
            text("""
                SELECT e.event_id, e.occurred_at, e.job_id, e.soldier_id,
                       e.persona_id, e.platform, s.current_name,
                       e.collector_uuid, e.collector_name_snapshot,
                       e.hostname_snapshot, e.egress_key_snapshot,
                       e.attempt_number, e.result, e.duration_ms,
                       e.http_status, e.error_class, e.error_message,
                       e.lease_token, e.metadata,
                       cs.detailed_state, cs.detailed_last_attempt_at,
                       cs.detailed_last_success_at, cs.detailed_next_due_at,
                       cs.detailed_consecutive_failures,
                       cs.detailed_last_error_class,
                       cs.detailed_last_error_message,
                       (dsc.soldier_id IS NOT NULL) AS has_current,
                       (SELECT count(*) FROM detailed_stats_history dsh
                         WHERE dsh.soldier_id = e.soldier_id) AS history_rows
                FROM collection_events e
                JOIN soldiers s ON s.soldier_id = e.soldier_id
                JOIN collection_state cs ON cs.soldier_id = e.soldier_id
                LEFT JOIN detailed_stats_current dsc ON dsc.soldier_id = e.soldier_id
                WHERE e.resource = 'detailed'
                  AND e.lane = 'background'
                  AND e.soldier_id IN :ids
                  AND e.event_type = 'collection_failure'
                ORDER BY e.event_id
            """).bindparams(ids_param), {"ids": ids}
        ).mappings().all()

        residual_jobs = conn.execute(
            text("""
                SELECT job_id, soldier_id, status, attempt_count, collector_uuid,
                       lease_token, last_error_class, last_error_at
                FROM collection_jobs
                WHERE resource = 'detailed'
                  AND soldier_id IN :ids
                ORDER BY soldier_id
            """).bindparams(ids_param), {"ids": ids}
        ).mappings().all()

    print("===== BF4PS PHASE 4B FAILURE FORENSICS =====")
    print("mode=read-only database reconciliation")
    print(f"frozen cohort: {len(ids)} PC soldiers")
    print(f"terminal detailed failures: {len(failures)}")
    print(f"residual cohort detailed jobs: {len(residual_jobs)}")

    fingerprints = Counter(
        (
            row["http_status"],
            row["error_class"],
            row["error_message"],
            row["detailed_state"],
            row["detailed_last_error_class"],
            row["detailed_last_error_message"],
        )
        for row in failures
    )

    print("\n===== FAILURE FINGERPRINTS =====")
    if not fingerprints:
        print("none")
    for fingerprint, count in fingerprints.most_common():
        http_status, error_class, error_message, state, state_class, state_message = fingerprint
        print(f"count={count}")
        print(f"  event http_status={http_status!r} error_class={error_class!r}")
        print(f"  event error_message={error_message!r}")
        print(f"  state={state!r} state_error_class={state_class!r}")
        print(f"  state_error_message={state_message!r}")

    print("\n===== INDIVIDUAL FAILURES =====")
    for index, row in enumerate(failures, 1):
        print(f"\n--- FAILURE {index}/{len(failures)} ---")
        print(
            f"event={row['event_id']} occurred={row['occurred_at']} "
            f"job={row['job_id']} attempt={row['attempt_number']} duration_ms={row['duration_ms']}"
        )
        print(
            f"soldier={row['soldier_id']} persona={row['persona_id']} "
            f"platform={row['platform']!r} name={row['current_name']!r}"
        )
        print(
            f"collector={row['collector_name_snapshot']!r} host={row['hostname_snapshot']!r} "
            f"egress={row['egress_key_snapshot']!r} uuid={row['collector_uuid']}"
        )
        print(
            f"result={row['result']!r} http_status={row['http_status']!r} "
            f"error_class={row['error_class']!r}"
        )
        print(f"error_message={row['error_message']!r}")
        print(
            f"state={row['detailed_state']!r} last_attempt={row['detailed_last_attempt_at']} "
            f"last_success={row['detailed_last_success_at']} next_due={row['detailed_next_due_at']}"
        )
        print(
            f"consecutive_failures={row['detailed_consecutive_failures']} "
            f"state_error_class={row['detailed_last_error_class']!r}"
        )
        print(f"state_error_message={row['detailed_last_error_message']!r}")
        print(f"has_current={row['has_current']} history_rows={row['history_rows']}")
        print(f"lease_token={row['lease_token']}")
        print("metadata=" + json.dumps(row["metadata"], sort_keys=True, default=str))

    if residual_jobs:
        print("\n===== RESIDUAL JOBS =====")
        for row in residual_jobs:
            print(dict(row))

    print("\ndatabase writes: 0")
    print("Battlelog requests: 0")
    print("PHASE 4B FAILURE FORENSICS: COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
