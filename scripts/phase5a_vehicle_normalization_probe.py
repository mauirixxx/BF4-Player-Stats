#!/usr/bin/env python3
"""One-request, zero-write live vehicle normalization probe for Phase 5A."""

from __future__ import annotations

from collections import Counter

from bf4ps.battlelog_vehicles import fetch_vehicle_stats, normalize_vehicle_stats
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT


def main() -> int:
    soldier_id, persona_id, player_name, platform = FROZEN_COHORT[0]

    print("===== BF4PS PHASE 5A LIVE VEHICLE NORMALIZATION PROBE =====")
    print(
        f"soldier={soldier_id} persona={persona_id} "
        f"name={player_name!r} platform={platform}"
    )
    print("database writes: 0")
    print("Battlelog requests: exactly 1")

    fetched = fetch_vehicle_stats(persona_id, platform)
    rows = normalize_vehicle_stats(
        fetched.payload,
        expected_persona_id=persona_id,
        expected_platform_int=fetched.platform_int,
    )

    if len(rows) != 82:
        raise RuntimeError(
            f"expected 82 normalized vehicle rows from validated live contract; got {len(rows)}"
        )

    guid_count = len({row.vehicle_guid for row in rows})
    if guid_count != len(rows):
        raise RuntimeError(
            f"normalized vehicle GUIDs are not unique: rows={len(rows)} unique={guid_count}"
        )

    destroy_null = sum(row.destroy_x_in_y is None for row in rows)
    slug_null = sum(row.slug is None for row in rows)
    category_null = sum(row.category is None for row in rows)
    destroy_non_integral = sum(
        row.destroy_x_in_y is not None
        and row.destroy_x_in_y != row.destroy_x_in_y.to_integral_value()
        for row in rows
    )
    categories = Counter(row.category for row in rows)

    print(f"http_status=200")
    print(f"response_bytes={fetched.response_bytes}")
    print(f"normalized_rows={len(rows)}")
    print(f"unique_vehicle_guids={guid_count}")
    print(f"slug_null_rows={slug_null}")
    print(f"category_null_rows={category_null}")
    print(f"destroy_x_in_y_null_rows={destroy_null}")
    print(f"destroy_x_in_y_non_integral_rows={destroy_non_integral}")
    print(f"kills_range={min(row.kills for row in rows)}..{max(row.kills for row in rows)}")
    print(
        "time_in_seconds_range="
        f"{min(row.time_in_seconds for row in rows)}..{max(row.time_in_seconds for row in rows)}"
    )
    print(f"distinct_categories={len(categories)}")
    print("database writes: 0")
    print("Battlelog requests: 1")
    print("PHASE 5A LIVE VEHICLE NORMALIZATION PROBE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
