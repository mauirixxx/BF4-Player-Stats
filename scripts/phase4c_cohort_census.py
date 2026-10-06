#!/usr/bin/env python3
"""Read-only Phase 4C census and deterministic 150/150/150 cohort export.

The census selects untouched detailed-stat soldiers independently per platform
so ascending global soldier_id order cannot turn the cohort into a PC-only
sample. It writes no database rows and makes no Battlelog requests.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text

EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_ALEMBIC = "0003_request_gates"
PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 150
TOTAL = PER_PLATFORM * len(PLATFORMS)
OUTPUT_PATH = Path(__file__).with_name("phase4c_cohort.py")


def assert_target(conn) -> None:
    row = conn.execute(text("""
        SELECT current_database() AS database_name,
               pg_is_in_recovery() AS recovery,
               current_setting('transaction_read_only') AS read_only
    """)).mappings().one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if row["database_name"] != EXPECTED_DB or revision != EXPECTED_ALEMBIC:
        raise RuntimeError(
            f"REFUSING target database={row['database_name']!r} alembic={revision!r}; "
            f"expected {EXPECTED_DB!r}/{EXPECTED_ALEMBIC!r}"
        )
    if row["recovery"]:
        raise RuntimeError("REFUSING: connected database is a recovery replica")


def candidate_sql(limit: bool) -> str:
    suffix = "LIMIT :limit" if limit else ""
    return f"""
        SELECT s.soldier_id, s.persona_id, s.current_name, s.platform
        FROM soldiers AS s
        JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
        WHERE s.platform = :platform
          AND cs.detailed_state = 'never_attempted'
          AND NOT EXISTS (
                SELECT 1 FROM detailed_stats_current AS dsc
                WHERE dsc.soldier_id = s.soldier_id
          )
          AND NOT EXISTS (
                SELECT 1 FROM detailed_stats_history AS dsh
                WHERE dsh.soldier_id = s.soldier_id
          )
          AND NOT EXISTS (
                SELECT 1 FROM collection_jobs AS j
                WHERE j.soldier_id = s.soldier_id
                  AND j.resource = 'detailed'
          )
        ORDER BY s.soldier_id ASC
        {suffix}
    """


def render_cohort(rows) -> str:
    lines = [
        '\"\"\"Frozen Phase 4C 450-player multiplatform sustained cohort.',
        "",
        "Generated from the read-only Phase 4C census: exactly 150 PC,",
        "150 PS4, and 150 Xbox One soldiers. Identity fields are captured",
        "as evidence; soldier_id is the durable BF4PS database identity.",
        '\"\"\"',
        "from __future__ import annotations",
        "",
        "# (soldier_id, persona_id, current_name, platform)",
        "PHASE4C_COHORT = (",
    ]
    for row in rows:
        lines.append(
            f"    ({int(row['soldier_id'])}, {int(row['persona_id'])}, "
            f"{str(row['current_name'])!r}, {str(row['platform'])!r}),"
        )
    lines.extend([
        ")",
        "",
        "SOLDIER_IDS = tuple(row[0] for row in PHASE4C_COHORT)",
        "PERSONA_IDS = tuple(row[1] for row in PHASE4C_COHORT)",
        "PLATFORM_SOLDIER_IDS = {",
        "    platform: tuple(row[0] for row in PHASE4C_COHORT if row[3] == platform)",
        "    for platform in ('pc', 'ps4', 'xboxone')",
        "}",
        "",
        f"assert len(PHASE4C_COHORT) == {TOTAL}",
        f"assert len(set(SOLDIER_IDS)) == {TOTAL}",
        f"assert len(set(PERSONA_IDS)) == {TOTAL}",
        f"assert all(len(ids) == {PER_PLATFORM} for ids in PLATFORM_SOLDIER_IDS.values())",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        assert_target(conn)
        candidates = []
        eligible_counts = {}
        for platform in PLATFORMS:
            params = {"platform": platform, "limit": PER_PLATFORM}
            rows = conn.execute(text(candidate_sql(True)), params).mappings().all()
            candidates.extend(rows)
            eligible_counts[platform] = int(conn.execute(
                text("SELECT COUNT(*) FROM (" + candidate_sql(False) + ") AS eligible"),
                {"platform": platform},
            ).scalar_one())

        state_rows = conn.execute(text("""
            SELECT s.platform, cs.detailed_state, COUNT(*) AS n
            FROM collection_state AS cs
            JOIN soldiers AS s ON s.soldier_id = cs.soldier_id
            GROUP BY s.platform, cs.detailed_state
            ORDER BY s.platform, cs.detailed_state
        """)).all()
        counters = {
            "soldiers": int(conn.execute(text("SELECT COUNT(*) FROM soldiers")).scalar_one()),
            "current": int(conn.execute(text("SELECT COUNT(*) FROM detailed_stats_current")).scalar_one()),
            "history": int(conn.execute(text("SELECT COUNT(*) FROM detailed_stats_history")).scalar_one()),
            "events": int(conn.execute(text("SELECT COUNT(*) FROM collection_events")).scalar_one()),
            "jobs": int(conn.execute(text("SELECT COUNT(*) FROM collection_jobs")).scalar_one()),
            "detailed_background_jobs": int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE resource='detailed' AND lane='background'
            """)).scalar_one()),
        }
        max_event = conn.execute(text("SELECT MAX(event_id) FROM collection_events")).scalar_one()
        active_owned = int(conn.execute(text("""
            SELECT COUNT(*) FROM collectors
            WHERE retired_at IS NULL AND current_job_id IS NOT NULL
        """)).scalar_one())
        throttle = int(conn.execute(text("""
            SELECT COUNT(*) FROM collection_events
            WHERE http_status IN (403,429) OR error_class='battlelog_throttle'
        """)).scalar_one())

    ids = [int(row["soldier_id"]) for row in candidates]
    personas = [int(row["persona_id"]) for row in candidates]
    names = [str(row["current_name"]) for row in candidates]
    distribution = Counter(str(row["platform"]) for row in candidates)
    checks = [
        *[(f"at least 150 eligible untouched {p} soldiers", eligible_counts[p] >= PER_PLATFORM) for p in PLATFORMS],
        ("preview contains exactly 450 soldiers", len(candidates) == TOTAL),
        ("preview is exactly 150/150/150", all(distribution[p] == PER_PLATFORM for p in PLATFORMS)),
        ("preview soldier IDs unique", len(ids) == len(set(ids))),
        ("preview persona IDs unique", len(personas) == len(set(personas))),
        ("preview names non-empty", all(name.strip() for name in names)),
        ("no detailed/background queue exists at baseline", counters["detailed_background_jobs"] == 0),
        ("no active collector currently owns a job", active_owned == 0),
    ]

    print("===== BF4PS PHASE 4C MULTIPLATFORM COHORT CENSUS =====")
    for platform in PLATFORMS:
        print(f"eligible untouched {platform:<7} soldiers: {eligible_counts[platform]}")
    print(f"deterministic cohort size: {len(candidates)}/{TOTAL}")
    print("cohort distribution:", dict(distribution))
    print("starting database counters:")
    for key, value in counters.items():
        print(f"  {key:<25} {value}")
    print(f"  max_event_id              {max_event}")
    print("detailed collection-state distribution by platform:")
    for platform, state, n in state_rows:
        print(f"  {platform:<8} {state:<20} {n}")
    print(f"historical 403/429/throttle events: {throttle}")
    for platform in PLATFORMS:
        platform_rows = [row for row in candidates if row["platform"] == platform]
        if platform_rows:
            first, last = platform_rows[0], platform_rows[-1]
            print(f"{platform} cohort boundary:")
            print(f"  first soldier={first['soldier_id']} persona={first['persona_id']} name={first['current_name']!r}")
            print(f"  last  soldier={last['soldier_id']} persona={last['persona_id']} name={last['current_name']!r}")
    print("validation:")
    for label, ok in checks:
        print(f"{label:<62} {'PASS' if ok else 'FAIL'}")
    print("database writes: 0")
    print("Battlelog requests: 0")

    passed = all(ok for _, ok in checks)
    if passed:
        OUTPUT_PATH.write_text(render_cohort(candidates), encoding="utf-8")
        print(f"frozen cohort candidate written: {OUTPUT_PATH}")
        print("NOTE: file write only; database remains read-only")
    print(f"PHASE 4C MULTIPLATFORM COHORT CENSUS: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
