#!/usr/bin/env python3
"""Read-only Phase 4B census and deterministic 900-PC cohort preview/export.

The census deliberately excludes every soldier that already has a detailed
current/history row, any non-pristine detailed collection state, and any
soldier with an existing detailed collection job.  It writes no database rows
and makes no Battlelog requests.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text

EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_ALEMBIC = "0003_request_gates"
COHORT_SIZE = 900
OUTPUT_PATH = Path(__file__).with_name("phase4b_cohort.py")


def assert_target(conn) -> None:
    database = conn.execute(text("SELECT current_database()")).scalar_one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if database != EXPECTED_DB or revision != EXPECTED_ALEMBIC:
        raise RuntimeError(
            f"REFUSING target database={database!r} alembic={revision!r}; "
            f"expected {EXPECTED_DB!r}/{EXPECTED_ALEMBIC!r}"
        )


def candidate_sql(limit: bool) -> str:
    suffix = "LIMIT :limit" if limit else ""
    return f"""
        SELECT s.soldier_id, s.persona_id, s.current_name, s.platform
        FROM soldiers AS s
        JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
        WHERE s.platform = 'pc'
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
        '"""Frozen Phase 4B 900-player sustained PC cohort.',
        "",
        "Generated from the read-only Phase 4B census. Identity fields are",
        "captured as evidence; soldier_id is the durable BF4PS database identity.",
        '"""',
        "from __future__ import annotations",
        "",
        "# (soldier_id, persona_id, current_name, platform)",
        "PHASE4B_COHORT = (",
    ]
    for row in rows:
        lines.append(
            f"    ({int(row['soldier_id'])}, {int(row['persona_id'])}, "
            f"{str(row['current_name'])!r}, {str(row['platform'])!r}),"
        )
    lines.extend([
        ")",
        "",
        "SOLDIER_IDS = tuple(row[0] for row in PHASE4B_COHORT)",
        "PERSONA_IDS = tuple(row[1] for row in PHASE4B_COHORT)",
        "",
        f"assert len(PHASE4B_COHORT) == {COHORT_SIZE}",
        f"assert len(set(SOLDIER_IDS)) == {COHORT_SIZE}",
        f"assert len(set(PERSONA_IDS)) == {COHORT_SIZE}",
        'assert all(row[3] == "pc" for row in PHASE4B_COHORT)',
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
        candidates = conn.execute(
            text(candidate_sql(True)), {"limit": COHORT_SIZE}
        ).mappings().all()
        eligible_count = int(conn.execute(text(
            "SELECT COUNT(*) FROM (" + candidate_sql(False) + ") AS eligible"
        )).scalar_one())
        state_rows = conn.execute(text("""
            SELECT detailed_state, COUNT(*) AS n
            FROM collection_state
            GROUP BY detailed_state
            ORDER BY detailed_state
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
    checks = [
        ("at least 900 eligible untouched PC soldiers", eligible_count >= COHORT_SIZE),
        ("preview contains exactly 900 soldiers", len(candidates) == COHORT_SIZE),
        ("preview soldier IDs unique", len(ids) == len(set(ids))),
        ("preview persona IDs unique", len(personas) == len(set(personas))),
        ("preview names non-empty", all(name.strip() for name in names)),
        ("preview platforms all PC", all(row["platform"] == "pc" for row in candidates)),
        ("no detailed/background queue exists at baseline", counters["detailed_background_jobs"] == 0),
        ("no active collector currently owns a job", active_owned == 0),
    ]

    print("===== BF4PS PHASE 4B COHORT CENSUS =====")
    print(f"eligible untouched PC soldiers: {eligible_count}")
    print(f"deterministic cohort size:      {len(candidates)}/{COHORT_SIZE}")
    print("starting database counters:")
    for key, value in counters.items():
        print(f"  {key:<25} {value}")
    print(f"  max_event_id              {max_event}")
    print("detailed collection-state distribution:")
    for state, n in state_rows:
        print(f"  {state:<20} {n}")
    print(f"historical 403/429/throttle events: {throttle}")
    if candidates:
        first, last = candidates[0], candidates[-1]
        print("cohort boundary:")
        print(f"  first soldier={first['soldier_id']} persona={first['persona_id']} name={first['current_name']!r}")
        print(f"  last  soldier={last['soldier_id']} persona={last['persona_id']} name={last['current_name']!r}")
    print("validation:")
    for label, ok in checks:
        print(f"{label:<58} {'PASS' if ok else 'FAIL'}")
    print("database writes: 0")
    print("Battlelog requests: 0")

    passed = all(ok for _, ok in checks)
    if passed:
        OUTPUT_PATH.write_text(render_cohort(candidates), encoding="utf-8")
        print(f"frozen cohort candidate written: {OUTPUT_PATH}")
        print("NOTE: file write only; database remains read-only")
    print(f"PHASE 4B COHORT CENSUS: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
