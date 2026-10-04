#!/usr/bin/env python3
"""Read-only control-side preflight for the Phase 3D two-host frozen cohort."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
PER_PLATFORM = 4
PLATFORMS = ("pc", "ps4", "xboxone")
RESOURCE = "detailed"
LANE = "background"
MAX_ATTEMPTS = PER_PLATFORM * len(PLATFORMS)

FROZEN_COLLECTORS = (
    ("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d001", "phase3d-hnl-01", "hnl-01", "phase3d-hnl-01"),
    ("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d002", "phase3d-kah-01", "kah-01", "phase3d-kah-01"),
)


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        target = conn.execute(text("""
            SELECT current_database() AS database_name,
                   current_user AS database_user,
                   inet_server_addr()::text AS server_address,
                   inet_server_port() AS server_port,
                   pg_is_in_recovery() AS recovery,
                   current_setting('transaction_read_only') AS read_only
        """)).mappings().one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        queue = conn.execute(text("""
            SELECT job_id, soldier_id, status, collector_uuid, attempt_count
            FROM collection_jobs
            WHERE resource = :resource AND lane = :lane
            ORDER BY job_id
        """), {"resource": RESOURCE, "lane": LANE}).mappings().all()

        identities = conn.execute(text("""
            SELECT collector_uuid::text AS collector_uuid, collector_name, hostname,
                   lane, egress_key, enabled, drained, retired_at
            FROM collectors
            WHERE collector_uuid::text IN (:uuid_a, :uuid_b)
               OR lower(collector_name) IN (:name_a, :name_b)
            ORDER BY collector_name
        """), {
            "uuid_a": FROZEN_COLLECTORS[0][0], "uuid_b": FROZEN_COLLECTORS[1][0],
            "name_a": FROZEN_COLLECTORS[0][1], "name_b": FROZEN_COLLECTORS[1][1],
        }).mappings().all()

        gates = conn.execute(text("""
            SELECT egress_key, next_request_at, updated_at
            FROM request_gates
            WHERE egress_key IN (:egress_a, :egress_b)
            ORDER BY egress_key
        """), {
            "egress_a": FROZEN_COLLECTORS[0][3],
            "egress_b": FROZEN_COLLECTORS[1][3],
        }).mappings().all()

        rows = conn.execute(text("""
            WITH eligible AS (
                SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
                       cs.detailed_state, cs.detailed_last_attempt_at,
                       cs.detailed_last_success_at, dsc.source_fetched_at,
                       row_number() OVER (
                           PARTITION BY s.platform ORDER BY s.soldier_id ASC
                       ) AS platform_rank
                FROM soldiers AS s
                JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
                LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
                WHERE s.platform IN ('pc', 'ps4', 'xboxone')
                  AND cs.detailed_state = 'never_attempted'
                  AND cs.detailed_last_attempt_at IS NULL
                  AND cs.detailed_last_success_at IS NULL
                  AND dsc.soldier_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM collection_jobs AS j
                      WHERE j.soldier_id = s.soldier_id
                        AND j.resource = 'detailed'
                  )
            )
            SELECT soldier_id, persona_id, platform, current_name,
                   detailed_state, detailed_last_attempt_at,
                   detailed_last_success_at, source_fetched_at
            FROM eligible
            WHERE platform_rank <= :per_platform
            ORDER BY CASE platform
                         WHEN 'pc' THEN 1 WHEN 'ps4' THEN 2 WHEN 'xboxone' THEN 3
                     END, soldier_id ASC
        """), {"per_platform": PER_PLATFORM}).mappings().all()

    print("===== BF4PS PHASE 3D FROZEN-COHORT PREFLIGHT =====\n")
    print("READ-ONLY CONTROL-SIDE PREFLIGHT")
    print("No collector registration, feeder pass, queue write, job claim, or Battlelog request is performed.\n")
    print(f"database:       {target['database_name']}")
    print(f"database user:  {target['database_user']}")
    print(f"server address: {target['server_address']}:{target['server_port']}")
    print(f"recovery:       {target['recovery']}")
    print(f"read only:      {target['read_only']}")
    print(f"alembic:        {revision}")
    print(f"resource/lane:  {RESOURCE}/{LANE}")
    print(f"platform mix:   {PER_PLATFORM}/{PER_PLATFORM}/{PER_PLATFORM}")
    print(f"global ceiling: {MAX_ATTEMPTS}")

    if target["database_name"] != EXPECTED_DATABASE:
        raise SystemExit(f"REFUSING: expected {EXPECTED_DATABASE}, found {target['database_name']}")
    if target["recovery"] or target["read_only"] != "off":
        raise SystemExit("REFUSING: PostgreSQL target is not a writable primary")
    if revision != EXPECTED_REVISION:
        raise SystemExit(f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}")

    print("\n===== FROZEN COLLECTOR IDENTITIES =====")
    if identities:
        for row in identities:
            print(dict(row))
    else:
        print("(none materialized — expected before execution)")

    print("\n===== FROZEN EGRESS GATES =====")
    if gates:
        for row in gates:
            print(dict(row))
    else:
        print("(none materialized — expected before execution)")

    print("\n===== EXISTING DETAILED/BACKGROUND QUEUE =====")
    if queue:
        for row in queue:
            print(dict(row))
    else:
        print("(empty)")

    print("\n===== PROPOSED FROZEN COHORT =====")
    counts = {platform: 0 for platform in PLATFORMS}
    for row in rows:
        counts[row["platform"]] += 1
        print(
            f"soldier={row['soldier_id']:<7} {row['platform']:<8} "
            f"persona={row['persona_id']:<13} {row['current_name']!r}"
        )

    exact_mix = all(counts[p] == PER_PLATFORM for p in PLATFORMS)
    exact_size = len(rows) == MAX_ATTEMPTS
    pristine = all(
        row["detailed_state"] == "never_attempted"
        and row["detailed_last_attempt_at"] is None
        and row["detailed_last_success_at"] is None
        and row["source_fetched_at"] is None
        for row in rows
    )

    print("\n===== PLATFORM COUNTS =====")
    for platform in PLATFORMS:
        print(f"{platform:<8} {counts[platform]}/{PER_PLATFORM}")

    print("\n===== SAFETY DECISION =====")
    print("expected BF4PS test database:        PASS")
    print("writable PostgreSQL primary:         PASS")
    print("expected Alembic head:               PASS")
    print(f"existing detailed/background queue: {'EMPTY' if not queue else 'NOT EMPTY'}")
    print(f"frozen collector conflicts:          {'NONE' if not identities else 'PRESENT'}")
    print(f"frozen request gates pre-existing:   {'NONE' if not gates else 'PRESENT'}")
    print(f"exact 4/4/4 platform mix:            {'PASS' if exact_mix else 'FAIL'}")
    print(f"exactly 12 candidates found:         {'PASS' if exact_size else 'FAIL'}")
    print(f"cohort pristine:                     {'PASS' if pristine else 'FAIL'}")
    print(f"hard global attempt/job ceiling:     {MAX_ATTEMPTS}")
    print("external Battlelog requests:         0")
    print("database writes:                     0")

    if queue:
        raise SystemExit("PREFLIGHT FAIL: detailed/background queue is not empty")
    if identities:
        raise SystemExit("PREFLIGHT FAIL: frozen collector identity/name already materialized")
    if gates:
        raise SystemExit("PREFLIGHT FAIL: frozen request gate already materialized")
    if not exact_mix or not exact_size or not pristine:
        raise SystemExit("PREFLIGHT FAIL: exact pristine 4 PC / 4 PS4 / 4 Xbox One cohort unavailable")

    print("\nPHASE 3D FROZEN-COHORT PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
