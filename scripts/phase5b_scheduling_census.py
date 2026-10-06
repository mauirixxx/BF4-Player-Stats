#!/usr/bin/env python3
"""Read-only Phase 5B production scheduling census.

This script makes no database writes and no Battlelog requests.  It reports
population/source recency, collection freshness, retry debt, queue pressure,
collector/request-gate inventory, and durable historical request volume.
"""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
RESOURCES = ("detailed", "profile", "weapons", "vehicles")
AGE_BUCKETS = (
    ("lt_1h", "interval '1 hour'"),
    ("1h_6h", "interval '6 hours'"),
    ("6h_24h", "interval '24 hours'"),
    ("1d_7d", "interval '7 days'"),
    ("7d_30d", "interval '30 days'"),
)


def assert_target(conn) -> None:
    database = str(conn.execute(text("SELECT current_database()")).scalar_one())
    revision = str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
    if database != EXPECTED_DATABASE:
        raise RuntimeError(f"REFUSING: expected database {EXPECTED_DATABASE!r}, got {database!r}")
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"REFUSING: expected Alembic revision {EXPECTED_REVISION!r}, got {revision!r}")


def print_rows(rows, columns) -> None:
    if not rows:
        print("  none")
        return
    for row in rows:
        print("  " + " ".join(f"{column}={row[column]}" for column in columns))


def main() -> int:
    print("===== BF4PS PHASE 5B PRODUCTION SCHEDULING CENSUS =====")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("source recency is discovery/source observation, NOT proven gameplay activity")

    engine = make_engine()
    with engine.connect() as conn:
        assert_target(conn)

        population = conn.execute(text("""
            SELECT platform, count(*) AS soldiers
            FROM soldiers
            GROUP BY platform
            ORDER BY platform
        """)).mappings().all()
        total = int(conn.execute(text("SELECT count(*) FROM soldiers")).scalar_one())

        source_types = conn.execute(text("""
            SELECT source_type, count(DISTINCT soldier_id) AS soldiers
            FROM soldier_sources
            GROUP BY source_type
            ORDER BY source_type
        """)).mappings().all()

        source_recency = conn.execute(text("""
            WITH latest AS (
                SELECT soldier_id, max(last_seen_at) AS last_seen_at
                FROM soldier_sources
                GROUP BY soldier_id
            )
            SELECT
                count(*) FILTER (WHERE last_seen_at > now() - interval '1 hour') AS lt_1h,
                count(*) FILTER (WHERE last_seen_at <= now() - interval '1 hour'
                                  AND last_seen_at > now() - interval '6 hours') AS h1_6,
                count(*) FILTER (WHERE last_seen_at <= now() - interval '6 hours'
                                  AND last_seen_at > now() - interval '24 hours') AS h6_24,
                count(*) FILTER (WHERE last_seen_at <= now() - interval '24 hours'
                                  AND last_seen_at > now() - interval '7 days') AS d1_7,
                count(*) FILTER (WHERE last_seen_at <= now() - interval '7 days'
                                  AND last_seen_at > now() - interval '30 days') AS d7_30,
                count(*) FILTER (WHERE last_seen_at <= now() - interval '30 days') AS gte_30d
            FROM latest
        """)).mappings().one()

        state_rows = {}
        freshness_rows = {}
        failure_rows = {}
        for resource in RESOURCES:
            state_rows[resource] = conn.execute(text(f"""
                SELECT {resource}_state AS state, count(*) AS soldiers
                FROM collection_state
                GROUP BY {resource}_state
                ORDER BY {resource}_state
            """)).mappings().all()
            freshness_rows[resource] = conn.execute(text(f"""
                SELECT
                    count(*) FILTER (WHERE {resource}_last_success_at > now() - interval '1 hour') AS lt_1h,
                    count(*) FILTER (WHERE {resource}_last_success_at <= now() - interval '1 hour'
                                      AND {resource}_last_success_at > now() - interval '6 hours') AS h1_6,
                    count(*) FILTER (WHERE {resource}_last_success_at <= now() - interval '6 hours'
                                      AND {resource}_last_success_at > now() - interval '24 hours') AS h6_24,
                    count(*) FILTER (WHERE {resource}_last_success_at <= now() - interval '24 hours'
                                      AND {resource}_last_success_at > now() - interval '7 days') AS d1_7,
                    count(*) FILTER (WHERE {resource}_last_success_at <= now() - interval '7 days'
                                      AND {resource}_last_success_at > now() - interval '30 days') AS d7_30,
                    count(*) FILTER (WHERE {resource}_last_success_at <= now() - interval '30 days') AS gte_30d,
                    count(*) FILTER (WHERE {resource}_last_success_at IS NULL) AS never_success
                FROM collection_state
            """)).mappings().one()
            failure_rows[resource] = conn.execute(text(f"""
                SELECT {resource}_state AS state,
                       coalesce({resource}_last_error_class, '<none>') AS error_class,
                       count(*) AS soldiers,
                       max({resource}_consecutive_failures) AS max_consecutive_failures
                FROM collection_state
                WHERE {resource}_state IN ('temporary_failure','unavailable')
                   OR {resource}_consecutive_failures > 0
                GROUP BY {resource}_state, coalesce({resource}_last_error_class, '<none>')
                ORDER BY soldiers DESC, state, error_class
            """)).mappings().all()

        queue = conn.execute(text("""
            SELECT resource, lane, priority_class, status,
                   count(*) AS jobs,
                   count(*) FILTER (
                       WHERE status IN ('claimed','running')
                          OR (status='pending' AND eligible_at <= now())
                   ) AS actionable,
                   count(*) FILTER (
                       WHERE status='pending' AND eligible_at > now()
                   ) AS cooldown
            FROM collection_jobs
            GROUP BY resource, lane, priority_class, status
            ORDER BY resource, lane, priority_class, status
        """)).mappings().all()

        collectors = conn.execute(text("""
            SELECT collector_name, hostname, lane, egress_key, enabled, drained,
                   heartbeat_state, current_job_id, retired_at
            FROM collectors
            ORDER BY retired_at NULLS FIRST, hostname, collector_name
        """)).mappings().all()

        gates = conn.execute(text("""
            SELECT egress_key, next_request_at, updated_at
            FROM request_gates
            ORDER BY egress_key
        """)).mappings().all()

        event_rates = conn.execute(text("""
            SELECT resource,
                   count(*) FILTER (
                       WHERE event_type='collection_attempt_started'
                         AND occurred_at > now() - interval '1 hour'
                   ) AS attempts_1h,
                   count(*) FILTER (
                       WHERE event_type='collection_attempt_started'
                         AND occurred_at > now() - interval '24 hours'
                   ) AS attempts_24h,
                   count(*) FILTER (
                       WHERE event_type IN ('collection_success','collection_failure')
                         AND occurred_at > now() - interval '24 hours'
                   ) AS terminal_24h,
                   count(*) FILTER (
                       WHERE event_type IN ('collection_success','collection_failure')
                         AND occurred_at > now() - interval '24 hours'
                         AND (http_status IN (403,429) OR error_class='battlelog_throttle')
                   ) AS throttle_24h
            FROM collection_events
            WHERE resource IS NOT NULL
            GROUP BY resource
            ORDER BY resource
        """)).mappings().all()

        all_time_attempts = conn.execute(text("""
            SELECT resource, count(*) AS attempts
            FROM collection_events
            WHERE event_type='collection_attempt_started'
              AND resource IS NOT NULL
            GROUP BY resource
            ORDER BY resource
        """)).mappings().all()

    print("\n===== POPULATION =====")
    print(f"total soldiers={total}")
    print_rows(population, ("platform", "soldiers"))

    print("\n===== SOURCE COVERAGE =====")
    print_rows(source_types, ("source_type", "soldiers"))
    print("latest source-observation recency:")
    print(
        "  <1h={lt_1h} 1-6h={h1_6} 6-24h={h6_24} 1-7d={d1_7} "
        "7-30d={d7_30} >=30d={gte_30d}".format(**source_recency)
    )

    print("\n===== COLLECTION STATE + SUCCESS FRESHNESS =====")
    for resource in RESOURCES:
        print(f"{resource}:")
        print("  states:")
        print_rows(state_rows[resource], ("state", "soldiers"))
        f = freshness_rows[resource]
        print(
            "  success age: <1h={lt_1h} 1-6h={h1_6} 6-24h={h6_24} "
            "1-7d={d1_7} 7-30d={d7_30} >=30d={gte_30d} "
            "never_success={never_success}".format(**f)
        )
        print("  failure/retry debt:")
        print_rows(failure_rows[resource], ("state", "error_class", "soldiers", "max_consecutive_failures"))

    print("\n===== QUEUE PRESSURE =====")
    print_rows(queue, ("resource", "lane", "priority_class", "status", "jobs", "actionable", "cooldown"))

    print("\n===== COLLECTORS =====")
    print_rows(
        collectors,
        ("collector_name", "hostname", "lane", "egress_key", "enabled", "drained",
         "heartbeat_state", "current_job_id", "retired_at"),
    )

    print("\n===== REQUEST GATES =====")
    print_rows(gates, ("egress_key", "next_request_at", "updated_at"))

    print("\n===== DURABLE REQUEST HISTORY =====")
    print("last 1h / 24h:")
    print_rows(event_rates, ("resource", "attempts_1h", "attempts_24h", "terminal_24h", "throttle_24h"))
    print("all-time durable attempt-start markers:")
    print_rows(all_time_attempts, ("resource", "attempts"))

    print("\nPHASE 5B PRODUCTION SCHEDULING CENSUS: COMPLETE")
    print("interpretation note: this report describes observed DB state; it does not choose production cadences")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
