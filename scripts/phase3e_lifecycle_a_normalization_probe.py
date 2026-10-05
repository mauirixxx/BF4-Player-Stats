#!/usr/bin/env python3
"""Read-only Battlelog normalization probe for Lifecycle A failed jobs.

This diagnostic deliberately bypasses the durable collection queue and request
 gate. It reads the identities attached to the frozen failed job IDs, fetches
Battlelog directly, runs the production normalizer, and prints only a compact
structural summary. It performs no database writes and verifies that the
relevant durable database state is unchanged before exiting.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bf4ps.battlelog_detailed import (  # noqa: E402
    DECIMAL_FIELDS,
    INTEGER_FIELDS,
    DetailedStatsError,
    DetailedStatsNormalizationError,
    fetch_detailed_stats,
    normalize_detailed_stats,
)
from phase3e_lifecycle_a_common import (  # noqa: E402
    EXPECTED_DATABASE,
    EXPECTED_DB_HOST,
    REQUEST_INTERVAL_SECONDS,
    assert_target,
)

TARGET_JOB_IDS = (765, 766, 768, 769, 770, 771, 772, 773)


def _snapshot(conn) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], int]:
    jobs = conn.execute(
        text(
            """
            SELECT job_id, soldier_id, resource, lane, status, attempt_count,
                   eligible_at, collector_uuid, lease_token, claimed_at,
                   started_at, lease_expires_at, last_error_class, last_error_at,
                   updated_at
            FROM collection_jobs
            WHERE job_id = ANY(:job_ids)
            ORDER BY job_id
            """
        ),
        {"job_ids": list(TARGET_JOB_IDS)},
    ).tuples().all()
    soldier_ids = [int(row[1]) for row in jobs]
    states = conn.execute(
        text(
            """
            SELECT soldier_id, detailed_state, detailed_last_attempt_at,
                   detailed_last_success_at, detailed_next_due_at,
                   detailed_consecutive_failures, detailed_last_error_class,
                   detailed_last_error_message, updated_at
            FROM collection_state
            WHERE soldier_id = ANY(:soldier_ids)
            ORDER BY soldier_id
            """
        ),
        {"soldier_ids": soldier_ids},
    ).tuples().all() if soldier_ids else []
    event_count = int(
        conn.execute(
            text(
                """
                SELECT count(*)
                FROM collection_events
                WHERE job_id = ANY(:job_ids)
                """
            ),
            {"job_ids": list(TARGET_JOB_IDS)},
        ).scalar_one()
    )
    return list(jobs), list(states), event_count


def _identities(conn) -> list[Mapping[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT j.job_id, j.soldier_id, j.resource, j.status,
                   j.attempt_count, j.last_error_class,
                   s.persona_id, s.platform, s.current_name
            FROM collection_jobs AS j
            JOIN soldiers AS s ON s.soldier_id = j.soldier_id
            WHERE j.job_id = ANY(:job_ids)
            ORDER BY j.job_id
            """
        ),
        {"job_ids": list(TARGET_JOB_IDS)},
    ).mappings().all()
    if len(rows) != len(TARGET_JOB_IDS):
        found = {int(row["job_id"]) for row in rows}
        missing = sorted(set(TARGET_JOB_IDS) - found)
        raise RuntimeError(f"target job lookup incomplete; missing={missing}")
    for row in rows:
        if row["resource"] != "detailed":
            raise RuntimeError(f"job {row['job_id']} is not a detailed job")
        if row["platform"] != "ps4":
            raise RuntimeError(
                f"job {row['job_id']} platform changed: expected ps4, got {row['platform']!r}"
            )
    return list(rows)


def _inner(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    data = payload.get("data")
    if data is None:
        return payload
    return data if isinstance(data, Mapping) else None


def _summary(payload: Mapping[str, Any]) -> str:
    data = payload.get("data")
    inner = _inner(payload)
    general = inner.get("generalStats") if inner is not None else None
    general_count = len(general) if isinstance(general, Mapping) else None
    persona = inner.get("personaId") if inner is not None else None
    platform = inner.get("platformInt") if inner is not None else None
    return (
        f"root_keys={sorted(payload.keys())} "
        f"data_type={type(data).__name__ if 'data' in payload else '<absent>'} "
        f"generalStats_type={type(general).__name__ if inner is not None else '<unavailable>'} "
        f"generalStats_fields={general_count} personaId={persona!r} platformInt={platform!r}"
    )


def _suspect_value(payload: Mapping[str, Any], message: str) -> str | None:
    inner = _inner(payload)
    if inner is None:
        return None
    general = inner.get("generalStats")
    if not isinstance(general, Mapping):
        return None
    for source in tuple(INTEGER_FIELDS.values()) + tuple(DECIMAL_FIELDS.values()):
        if message.startswith(f"{source}:"):
            value = general.get(source, "<absent>")
            rendered = repr(value)
            if len(rendered) > 240:
                rendered = rendered[:237] + "..."
            return f"suspect_field={source!r} suspect_value={rendered}"
    return None


def main() -> None:
    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        assert_target(conn)
        before = _snapshot(conn)
        identities = _identities(conn)

    print("===== LIFECYCLE A NORMALIZATION PROBE =====")
    print(f"target_jobs={','.join(str(j) for j in TARGET_JOB_IDS)}")
    print("mode=direct HTTP + production normalizer; database writes=NONE")
    print(f"request_spacing_seconds={REQUEST_INTERVAL_SECONDS}")

    failures = 0
    for index, row in enumerate(identities):
        if index:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        print(
            f"\n--- job={row['job_id']} soldier={row['soldier_id']} "
            f"name={row['current_name']!r} persona={row['persona_id']} "
            f"platform={row['platform']} queue_status={row['status']} "
            f"attempts={row['attempt_count']} last_error={row['last_error_class']!r} ---"
        )
        try:
            fetched = fetch_detailed_stats(
                int(row["persona_id"]),
                str(row["platform"]),
                timeout_seconds=15.0,
            )
            print("response:", _summary(fetched.payload))
            try:
                normalized = normalize_detailed_stats(
                    fetched.payload,
                    expected_persona_id=int(row["persona_id"]),
                    expected_platform_int=fetched.platform_int,
                )
            except DetailedStatsNormalizationError as exc:
                failures += 1
                message = str(exc)
                print(f"NORMALIZATION FAILURE: {message}")
                suspect = _suspect_value(fetched.payload, message)
                if suspect:
                    print(suspect)
            else:
                populated = sum(value is not None for value in normalized.values())
                print(f"NORMALIZATION SUCCESS: populated_retained_fields={populated}/{len(normalized)}")
        except DetailedStatsError as exc:
            failures += 1
            print(f"FETCH/SOURCE FAILURE: {exc.__class__.__name__}: {exc}")

    with engine.connect() as conn:
        assert_target(conn)
        after = _snapshot(conn)
    if before != after:
        raise RuntimeError("SAFETY FAILURE: relevant durable database state changed during probe")

    print("\n===== SAFETY CHECK =====")
    print("PASS: target collection_jobs unchanged")
    print("PASS: target collection_state unchanged")
    print("PASS: target collection_events count unchanged")
    print(f"probe_failures={failures}/{len(identities)}")


if __name__ == "__main__":
    main()
