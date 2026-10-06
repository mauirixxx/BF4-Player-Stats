#!/usr/bin/env python3
"""Read-only safety preflight for the Phase 4A sustained collection run."""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
import sys
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase4a_cohort import PHASE4A_COHORT, SOLDIER_IDS
from phase4a_common import EXPECTED_DATABASE, EXPECTED_DB_HOST, FROZEN_UUIDS, HOSTS, assert_target


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    engine = create_engine(url, pool_pre_ping=True)
    ids = list(SOLDIER_IDS)
    expected = {row[0]: row for row in PHASE4A_COHORT}

    with engine.connect() as conn:
        assert_target(conn)

        soldiers = conn.execute(
            text("""
                SELECT soldier_id, persona_id, current_name, platform
                FROM soldiers
                WHERE soldier_id = ANY(:ids)
                ORDER BY soldier_id
            """),
            {"ids": ids},
        ).mappings().all()
        identity_exact = len(soldiers) == len(ids) and all(
            (int(r["soldier_id"]), int(r["persona_id"]), str(r["current_name"]), str(r["platform"]))
            == expected[int(r["soldier_id"])]
            for r in soldiers
        )

        states = conn.execute(
            text("""
                SELECT soldier_id, detailed_state, detailed_last_attempt_at,
                       detailed_last_success_at, detailed_next_due_at,
                       detailed_consecutive_failures, detailed_last_error_class,
                       detailed_last_error_message
                FROM collection_state
                WHERE soldier_id = ANY(:ids)
                ORDER BY soldier_id
            """),
            {"ids": ids},
        ).mappings().all()
        state_dist = Counter(str(r["detailed_state"]) for r in states)
        pristine = len(states) == len(ids) and all(
            r["detailed_state"] == "never_attempted"
            and r["detailed_last_attempt_at"] is None
            and r["detailed_last_success_at"] is None
            and r["detailed_next_due_at"] is None
            and int(r["detailed_consecutive_failures"]) == 0
            and r["detailed_last_error_class"] is None
            and r["detailed_last_error_message"] is None
            for r in states
        )

        cohort_jobs = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource='detailed' AND soldier_id = ANY(:ids)
        """), {"ids": ids}).scalar_one())
        foreign_jobs = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource='detailed' AND lane='background'
              AND soldier_id <> ALL(:ids)
        """), {"ids": ids}).scalar_one())

        collectors = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, egress_key,
                   enabled, drained, heartbeat_state, current_job_id, retired_at
            FROM collectors
            WHERE collector_uuid = ANY(:uuids)
            ORDER BY hostname
        """), {"uuids": list(FROZEN_UUIDS)}).mappings().all()
        collector_exact = len(collectors) == 3 and all(
            r["retired_at"] is None
            and r["hostname"] in HOSTS
            and r["collector_uuid"] == HOSTS[r["hostname"]].collector_uuid
            and r["collector_name"] == HOSTS[r["hostname"]].collector_name
            and r["egress_key"] == HOSTS[r["hostname"]].egress_key
            and bool(r["enabled"])
            and not bool(r["drained"])
            and r["current_job_id"] is None
            for r in collectors
        )
        any_owned = int(conn.execute(text("""
            SELECT count(*) FROM collectors
            WHERE retired_at IS NULL AND current_job_id IS NOT NULL
        """)).scalar_one())

        gates = conn.execute(text("""
            SELECT egress_key, next_request_at, updated_at
            FROM request_gates
            WHERE egress_key = ANY(:keys)
            ORDER BY egress_key
        """), {"keys": [h.egress_key for h in HOSTS.values()]}).mappings().all()
        gate_exact = {r["egress_key"] for r in gates} == {h.egress_key for h in HOSTS.values()}

        prior_terminal = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='detailed' AND lane='background'
              AND soldier_id = ANY(:ids)
              AND event_type IN ('collection_success','collection_failure')
        """), {"ids": ids}).scalar_one())

        counters = {
            "current": int(conn.execute(text("SELECT count(*) FROM detailed_stats_current")).scalar_one()),
            "history": int(conn.execute(text("SELECT count(*) FROM detailed_stats_history")).scalar_one()),
            "events": int(conn.execute(text("SELECT count(*) FROM collection_events")).scalar_one()),
            "jobs": int(conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()),
            "max_event_id": conn.execute(text("SELECT max(event_id) FROM collection_events")).scalar_one(),
        }
        throttle = conn.execute(text("""
            SELECT http_status, count(*) AS n
            FROM collection_events
            WHERE http_status IN (403,429)
            GROUP BY http_status ORDER BY http_status
        """)).all()

    print("===== BF4PS PHASE 4A SUSTAINED-RUN PREFLIGHT =====")
    print(f"frozen cohort: {len(ids)} PC soldiers")
    print(f"state distribution: {dict(state_dist)}")
    print("starting counters:")
    for key, value in counters.items():
        print(f"  {key:<14} {value}")
    print("collectors:")
    for row in collectors:
        print(
            f"  {row['hostname']:<7} {row['collector_name']:<18} egress={row['egress_key']!r} "
            f"enabled={row['enabled']} drained={row['drained']} heartbeat={row['heartbeat_state']} current_job={row['current_job_id']}"
        )
    print("request gates:")
    for row in gates:
        print(f"  {row['egress_key']:<18} next={row['next_request_at']} updated={row['updated_at']}")
    print("historical 403/429:", "none" if not throttle else dict(throttle))

    checks = [
        ("exact frozen identities unchanged", identity_exact),
        ("all 90 detailed states pristine", pristine),
        ("no frozen-cohort detailed jobs exist", cohort_jobs == 0),
        ("no foreign detailed/background jobs exist", foreign_jobs == 0),
        ("three stable collectors exact/enabled/undrained/idle", collector_exact),
        ("no active collector owns any job", any_owned == 0),
        ("three required request gates exist", gate_exact),
        ("no prior Phase 4A terminal events", prior_terminal == 0),
    ]
    print("validation:")
    for label, ok in checks:
        print(f"{label:<58} {'PASS' if ok else 'FAIL'}")
    print("database writes: 0")
    print("Battlelog requests: 0")
    passed = all(ok for _, ok in checks)
    print(f"PHASE 4A SUSTAINED-RUN PREFLIGHT: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
