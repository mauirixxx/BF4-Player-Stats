#!/usr/bin/env python3
"""Read-only Phase 5B BF4SW source arrival/churn analysis.

The current schema retains first_seen_at and latest last_seen_at per soldier
source, not every source observation. Therefore this report can measure exact
new-arrival timing and current last-touch distributions, but it cannot
reconstruct historical observation-event volume.
"""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
SOURCE_TYPE = "bf4sw"


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
    print("===== BF4PS PHASE 5B BF4SW SOURCE ARRIVAL / CHURN ANALYSIS =====")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("historical touch-event volume: NOT DERIVABLE from current schema")
    print("reason: soldier_sources retains first_seen_at and latest last_seen_at, not every observation")

    engine = make_engine()
    with engine.connect() as conn:
        assert_target(conn)

        coverage = conn.execute(text("""
            SELECT count(*) AS source_rows,
                   count(DISTINCT soldier_id) AS soldiers,
                   min(first_seen_at) AS earliest_first_seen,
                   max(first_seen_at) AS latest_first_seen,
                   max(last_seen_at) AS latest_last_seen
            FROM soldier_sources
            WHERE source_type=:source_type
        """), {"source_type": SOURCE_TYPE}).mappings().one()

        arrivals_24h = conn.execute(text("""
            SELECT date_trunc('hour', ss.first_seen_at) AS bucket,
                   s.platform,
                   count(*) AS new_soldiers
            FROM soldier_sources ss
            JOIN soldiers s ON s.soldier_id=ss.soldier_id
            WHERE ss.source_type=:source_type
              AND ss.first_seen_at > now() - interval '24 hours'
            GROUP BY bucket, s.platform
            ORDER BY bucket, s.platform
        """), {"source_type": SOURCE_TYPE}).mappings().all()

        last_touch_24h = conn.execute(text("""
            SELECT date_trunc('hour', ss.last_seen_at) AS bucket,
                   s.platform,
                   count(*) AS soldiers_whose_latest_touch_is_here
            FROM soldier_sources ss
            JOIN soldiers s ON s.soldier_id=ss.soldier_id
            WHERE ss.source_type=:source_type
              AND ss.last_seen_at > now() - interval '24 hours'
            GROUP BY bucket, s.platform
            ORDER BY bucket, s.platform
        """), {"source_type": SOURCE_TYPE}).mappings().all()

        arrivals_30d = conn.execute(text("""
            SELECT date_trunc('day', ss.first_seen_at) AS bucket,
                   s.platform,
                   count(*) AS new_soldiers
            FROM soldier_sources ss
            JOIN soldiers s ON s.soldier_id=ss.soldier_id
            WHERE ss.source_type=:source_type
              AND ss.first_seen_at > now() - interval '30 days'
            GROUP BY bucket, s.platform
            ORDER BY bucket, s.platform
        """), {"source_type": SOURCE_TYPE}).mappings().all()

        last_touch_30d = conn.execute(text("""
            SELECT date_trunc('day', ss.last_seen_at) AS bucket,
                   s.platform,
                   count(*) AS soldiers_whose_latest_touch_is_here
            FROM soldier_sources ss
            JOIN soldiers s ON s.soldier_id=ss.soldier_id
            WHERE ss.source_type=:source_type
              AND ss.last_seen_at > now() - interval '30 days'
            GROUP BY bucket, s.platform
            ORDER BY bucket, s.platform
        """), {"source_type": SOURCE_TYPE}).mappings().all()

        lifetime = conn.execute(text("""
            SELECT
                count(*) FILTER (
                    WHERE last_seen_at = first_seen_at
                ) AS exact_single_timestamp,
                count(*) FILTER (
                    WHERE last_seen_at > first_seen_at
                      AND last_seen_at - first_seen_at < interval '1 hour'
                ) AS span_lt_1h,
                count(*) FILTER (
                    WHERE last_seen_at - first_seen_at >= interval '1 hour'
                      AND last_seen_at - first_seen_at < interval '24 hours'
                ) AS span_1h_24h,
                count(*) FILTER (
                    WHERE last_seen_at - first_seen_at >= interval '24 hours'
                      AND last_seen_at - first_seen_at < interval '7 days'
                ) AS span_1d_7d,
                count(*) FILTER (
                    WHERE last_seen_at - first_seen_at >= interval '7 days'
                      AND last_seen_at - first_seen_at < interval '30 days'
                ) AS span_7d_30d,
                count(*) FILTER (
                    WHERE last_seen_at - first_seen_at >= interval '30 days'
                ) AS span_gte_30d
            FROM soldier_sources
            WHERE source_type=:source_type
        """), {"source_type": SOURCE_TYPE}).mappings().one()

        recent_overlap = conn.execute(text("""
            SELECT
                count(*) FILTER (
                    WHERE first_seen_at > now() - interval '24 hours'
                ) AS new_24h,
                count(*) FILTER (
                    WHERE last_seen_at > now() - interval '24 hours'
                ) AS latest_touch_24h,
                count(*) FILTER (
                    WHERE first_seen_at > now() - interval '24 hours'
                      AND last_seen_at > first_seen_at
                ) AS new_24h_seen_again,
                count(*) FILTER (
                    WHERE first_seen_at <= now() - interval '24 hours'
                      AND last_seen_at > now() - interval '24 hours'
                ) AS returning_24h,
                count(*) FILTER (
                    WHERE first_seen_at > now() - interval '7 days'
                ) AS new_7d,
                count(*) FILTER (
                    WHERE last_seen_at > now() - interval '7 days'
                ) AS latest_touch_7d,
                count(*) FILTER (
                    WHERE first_seen_at <= now() - interval '7 days'
                      AND last_seen_at > now() - interval '7 days'
                ) AS returning_7d
            FROM soldier_sources
            WHERE source_type=:source_type
        """), {"source_type": SOURCE_TYPE}).mappings().one()

    print("\n===== SOURCE COVERAGE =====")
    print_rows([coverage], ("source_rows", "soldiers", "earliest_first_seen", "latest_first_seen", "latest_last_seen"))

    print("\n===== LAST 24 HOURS: EXACT NEW ARRIVALS BY HOUR =====")
    print_rows(arrivals_24h, ("bucket", "platform", "new_soldiers"))

    print("\n===== LAST 24 HOURS: CURRENT LAST-TOUCH DISTRIBUTION BY HOUR =====")
    print("NOTE: these are soldiers whose latest retained touch falls in each hour, not touch-event counts")
    print_rows(last_touch_24h, ("bucket", "platform", "soldiers_whose_latest_touch_is_here"))

    print("\n===== LAST 30 DAYS: EXACT NEW ARRIVALS BY DAY =====")
    print_rows(arrivals_30d, ("bucket", "platform", "new_soldiers"))

    print("\n===== LAST 30 DAYS: CURRENT LAST-TOUCH DISTRIBUTION BY DAY =====")
    print("NOTE: these are soldiers whose latest retained touch falls on each day, not touch-event counts")
    print_rows(last_touch_30d, ("bucket", "platform", "soldiers_whose_latest_touch_is_here"))

    print("\n===== OBSERVED SOURCE-LIFETIME SPAN =====")
    print("NOTE: first/last timestamps prove observation span, not number of observations")
    print_rows([lifetime], (
        "exact_single_timestamp", "span_lt_1h", "span_1h_24h",
        "span_1d_7d", "span_7d_30d", "span_gte_30d",
    ))

    print("\n===== RECENT NEW VS RETURNING IDENTITIES =====")
    print_rows([recent_overlap], (
        "new_24h", "latest_touch_24h", "new_24h_seen_again", "returning_24h",
        "new_7d", "latest_touch_7d", "returning_7d",
    ))

    print("\nPHASE 5B BF4SW SOURCE ARRIVAL / CHURN ANALYSIS: COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
