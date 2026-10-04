#!/usr/bin/env python3
"""Read-only verification of critical BF4PS PostgreSQL schema invariants.

Alembic migrations remain the executable source of truth. This harness protects
runtime SQL from drifting away from the schema documented in
``docs/database-schema-reference.md``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable

from sqlalchemy import create_engine, inspect, text

EXPECTED_REVISION = "0003_request_gates"
EXPECTED_TABLES = {
    "alembic_version",
    "soldiers",
    "soldier_sources",
    "soldier_names",
    "battlelog_profiles",
    "profile_soldiers",
    "detailed_stats_current",
    "detailed_stats_history",
    "weapon_catalog",
    "soldier_weapon_stats",
    "vehicle_catalog",
    "soldier_vehicle_stats",
    "collection_state",
    "discovery_state",
    "collectors",
    "collection_jobs",
    "collection_events",
    "request_gates",
}

DETAILED_FIELDS = {
    "rank", "time_played_seconds", "assault_score", "engineer_score",
    "support_score", "recon_score", "commander_score", "squad_score",
    "vehicle_score", "award_score", "unlock_score", "total_score",
    "combat_score", "conquest_score", "rush_score", "team_deathmatch_score",
    "domination_score", "obliteration_score", "defuse_score",
    "capture_the_flag_score", "air_superiority_score", "carrier_assault_score",
    "chain_link_score", "kills", "deaths", "kill_assists", "wins", "losses",
    "shots_fired", "shots_hit", "repairs", "revives", "heals", "resupplies",
    "avenger_kills", "savior_kills", "suppression_assists", "quit_percentage",
    "flags_captured", "flags_defended", "dogtags_taken", "vehicles_destroyed",
    "vehicle_damage", "headshots", "longest_headshot", "highest_kill_streak",
    "nemesis_kills", "highest_nemesis_streak",
}

EXPECTED_COLUMNS = {
    "soldiers": {
        "soldier_id", "persona_id", "platform", "current_name", "first_seen_at",
        "last_seen_at", "created_at", "updated_at",
    },
    "soldier_sources": {"soldier_id", "source_type", "first_seen_at", "last_seen_at"},
    "soldier_names": {"soldier_name_id", "soldier_id", "name", "first_seen_at", "last_seen_at"},
    "battlelog_profiles": {
        "profile_id", "battlelog_username", "battlelog_user_id", "country_code",
        "country_name", "access_state", "last_checked_at", "last_success_at",
        "last_error", "created_at", "updated_at",
    },
    "profile_soldiers": {"profile_id", "soldier_id", "first_seen_at", "last_seen_at"},
    "detailed_stats_current": {"soldier_id", "source_fetched_at", "updated_at"} | DETAILED_FIELDS,
    "detailed_stats_history": {"snapshot_id", "soldier_id", "observed_at"} | DETAILED_FIELDS,
    "weapon_catalog": {"weapon_id", "weapon_guid", "name", "slug", "category", "first_seen_at", "last_seen_at"},
    "soldier_weapon_stats": {
        "soldier_id", "weapon_id", "kills", "headshots", "shots_fired", "shots_hit",
        "time_equipped_seconds", "source_fetched_at", "updated_at",
    },
    "vehicle_catalog": {"vehicle_id", "vehicle_guid", "name", "slug", "category", "first_seen_at", "last_seen_at"},
    "soldier_vehicle_stats": {
        "soldier_id", "vehicle_id", "kills", "time_in_seconds", "destroy_x_in_y",
        "source_fetched_at", "updated_at",
    },
    "collection_state": {"soldier_id", "updated_at"} | {
        f"{resource}_{suffix}"
        for resource in ("detailed", "profile", "weapons", "vehicles")
        for suffix in (
            "state", "last_attempt_at", "last_success_at", "next_due_at",
            "consecutive_failures", "last_error_class", "last_error_message",
        )
    },
    "discovery_state": {"source_name", "last_alias_id", "last_poll_at", "last_success_at", "last_error", "updated_at"},
    "collectors": {
        "collector_uuid", "collector_name", "hostname", "lane", "egress_key",
        "enabled", "drained", "software_version", "started_at", "last_heartbeat_at",
        "heartbeat_state", "heartbeat_lost_at", "current_job_id", "created_at",
        "updated_at", "retired_at",
    },
    "collection_jobs": {
        "job_id", "soldier_id", "resource", "lane", "priority_class", "reason",
        "status", "priority_value", "eligible_at", "attempt_count", "collector_uuid",
        "lease_token", "claimed_at", "started_at", "lease_expires_at",
        "last_error_class", "last_error_at", "created_at", "updated_at",
    },
    "collection_events": {
        "event_id", "occurred_at", "collector_uuid", "collector_name_snapshot",
        "hostname_snapshot", "egress_key_snapshot", "job_id", "soldier_id",
        "persona_id", "platform", "resource", "lane", "event_type",
        "attempt_number", "result", "duration_ms", "http_status", "error_class",
        "error_message", "lease_token", "metadata",
    },
    "request_gates": {"egress_key", "next_request_at", "updated_at"},
}

EXPECTED_PKS = {
    "soldiers": ("soldier_id",),
    "soldier_sources": ("soldier_id", "source_type"),
    "soldier_names": ("soldier_name_id",),
    "battlelog_profiles": ("profile_id",),
    "profile_soldiers": ("profile_id", "soldier_id"),
    "detailed_stats_current": ("soldier_id",),
    "detailed_stats_history": ("snapshot_id",),
    "weapon_catalog": ("weapon_id",),
    "soldier_weapon_stats": ("soldier_id", "weapon_id"),
    "vehicle_catalog": ("vehicle_id",),
    "soldier_vehicle_stats": ("soldier_id", "vehicle_id"),
    "collection_state": ("soldier_id",),
    "discovery_state": ("source_name",),
    "collectors": ("collector_uuid",),
    "collection_jobs": ("job_id",),
    "collection_events": ("event_id",),
    "request_gates": ("egress_key",),
}

EXPECTED_UNIQUES = {
    "soldiers": {("persona_id", "platform")},
    "soldier_names": {("soldier_id", "name")},
    "collection_jobs": {("soldier_id", "resource")},
}

EXPECTED_FKS = {
    ("soldier_sources", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("soldier_names", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("profile_soldiers", ("profile_id",), "battlelog_profiles", ("profile_id",), "CASCADE"),
    ("profile_soldiers", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("detailed_stats_current", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("detailed_stats_history", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("soldier_weapon_stats", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("soldier_vehicle_stats", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("collection_state", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("collection_jobs", ("soldier_id",), "soldiers", ("soldier_id",), "CASCADE"),
    ("collection_jobs", ("collector_uuid",), "collectors", ("collector_uuid",), "SET NULL"),
    ("collectors", ("current_job_id",), "collection_jobs", ("job_id",), "SET NULL"),
    ("collection_events", ("collector_uuid",), "collectors", ("collector_uuid",), "SET NULL"),
    ("collection_events", ("soldier_id",), "soldiers", ("soldier_id",), "SET NULL"),
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"FAIL: {message}")


def pass_line(message: str) -> None:
    print(f"PASS: {message}")


def normalized_action(value: object) -> str:
    return str(value or "NO ACTION").upper().replace("_", " ")


def unique_sets(inspector, table: str) -> set[tuple[str, ...]]:
    values = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table)
        if item.get("column_names")
    }
    # PostgreSQL may expose unique indexes separately from constraints.
    values |= {
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(table)
        if item.get("unique") and item.get("column_names")
    }
    return values


def fk_set(inspector, tables: Iterable[str]) -> set[tuple[object, ...]]:
    result: set[tuple[object, ...]] = set()
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            options = fk.get("options") or {}
            result.add((
                table,
                tuple(fk.get("constrained_columns") or ()),
                fk.get("referred_table"),
                tuple(fk.get("referred_columns") or ()),
                normalized_action(options.get("ondelete")),
            ))
    return result


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("BF4PS_DATABASE_URL is not set")

    engine = create_engine(url)
    errors: list[str] = []

    print("===== BF4PS DATABASE SCHEMA VERIFICATION =====")
    print()
    print("READ-ONLY VALIDATION")
    print("No schema or data writes are performed by this script.")
    print()

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version" )).scalar_one()

    print(f"database: {db}")
    print(f"recovery: {recovery}")
    print(f"alembic:  {revision}")
    print()

    if "test" not in db.lower():
        print(f"REFUSING: schema verifier is intentionally restricted to test databases: {db}")
        return 2

    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())

    print("===== TABLES =====")
    missing_tables = EXPECTED_TABLES - actual_tables
    extra_tables = actual_tables - EXPECTED_TABLES
    if missing_tables:
        fail(errors, f"missing tables: {sorted(missing_tables)}")
    else:
        pass_line("all documented tables present")
    if extra_tables:
        fail(errors, f"undocumented tables present: {sorted(extra_tables)}")
    else:
        pass_line("no undocumented tables")

    if revision != EXPECTED_REVISION:
        fail(errors, f"Alembic revision {revision!r} != {EXPECTED_REVISION!r}")
    else:
        pass_line(f"Alembic revision is {EXPECTED_REVISION}")

    print()
    print("===== COLUMNS =====")
    for table, expected in EXPECTED_COLUMNS.items():
        if table not in actual_tables:
            continue
        actual = {column["name"] for column in inspector.get_columns(table)}
        missing = expected - actual
        extra = actual - expected
        if missing or extra:
            fail(errors, f"{table}: missing={sorted(missing)} extra={sorted(extra)}")
        else:
            pass_line(f"{table}: exact column set ({len(actual)})")

    print()
    print("===== PRIMARY KEYS =====")
    for table, expected in EXPECTED_PKS.items():
        if table not in actual_tables:
            continue
        actual = tuple(inspector.get_pk_constraint(table).get("constrained_columns") or ())
        if actual != expected:
            fail(errors, f"{table}: PK {actual!r} != {expected!r}")
        else:
            pass_line(f"{table}: {actual}")

    print()
    print("===== UNIQUE KEYS =====")
    for table, required in EXPECTED_UNIQUES.items():
        if table not in actual_tables:
            continue
        actual = unique_sets(inspector, table)
        missing = required - actual
        if missing:
            fail(errors, f"{table}: missing required unique keys {sorted(missing)}; actual={sorted(actual)}")
        else:
            pass_line(f"{table}: required unique keys present")

    print()
    print("===== FOREIGN KEYS / DELETE ACTIONS =====")
    actual_fks = fk_set(inspector, EXPECTED_COLUMNS)
    for expected in sorted(EXPECTED_FKS, key=str):
        if expected not in actual_fks:
            fail(errors, f"missing FK: {expected!r}")
        else:
            pass_line(str(expected))

    print()
    print("===== CRITICAL NEGATIVE ASSERTIONS =====")
    negatives = [
        ("collection_state", "resource"),
        ("detailed_stats_current", "observed_at"),
        ("detailed_stats_history", "source_fetched_at"),
        ("detailed_stats_current", "gun_master_score"),
        ("detailed_stats_history", "gun_master_score"),
    ]
    for table, column in negatives:
        actual = {item["name"] for item in inspector.get_columns(table)}
        if column in actual:
            fail(errors, f"{table}.{column} must be absent")
        else:
            pass_line(f"{table}.{column} absent")

    print()
    print("===== CRITICAL CHECKS / INDEXES =====")
    gate_checks = " ".join(str(item.get("sqltext", "")) for item in inspector.get_check_constraints("request_gates"))
    if "btrim(egress_key)" not in gate_checks:
        fail(errors, "request_gates non-empty egress_key check not found")
    else:
        pass_line("request_gates non-empty egress_key check present")

    history_indexes = inspector.get_indexes("detailed_stats_history")
    if not any((item.get("column_names") or [])[:2] == ["soldier_id", "observed_at"] for item in history_indexes):
        fail(errors, "detailed_stats_history soldier/observed index not found")
    else:
        pass_line("detailed_stats_history soldier/observed index present")

    print()
    print("===== RESULT =====")
    if errors:
        print(f"DATABASE SCHEMA VERIFICATION: FAIL ({len(errors)} discrepancy/discrepancies)")
        return 1

    print("DATABASE SCHEMA VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
