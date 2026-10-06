#!/usr/bin/env python3
"""One-request, zero-write Phase 5A vehicle payload shape inspector.

This deliberately does not normalize or persist vehicle data. It records enough
JSON structure to implement the vehicle normalizer from live evidence rather
than guessing Battlelog container keys or nullable field behavior.
"""
from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bf4ps.battlelog_detailed import BATTLELOG_BASE_URL, platform_int
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT

# First frozen PC soldier. Identity comes from the committed cohort artifact.
SOLDIER_ID, PERSONA_ID, PLAYER_NAME, PLATFORM = FROZEN_COHORT[0]


def _shape(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (int, float)):
        return type(value).__name__
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, Mapping):
        return f"object[{len(value)}]"
    return type(value).__name__


def _print_mapping(label: str, value: Mapping[str, Any]) -> None:
    print(f"\n===== {label} =====")
    for key in sorted(value):
        print(f"{key}: {_shape(value[key])}")


def main() -> int:
    p_int = platform_int(str(PLATFORM))
    url = (
        f"{BATTLELOG_BASE_URL}/bf4/warsawvehiclesPopulateStats/"
        f"{int(PERSONA_ID)}/{p_int}/stats/"
    )
    print("===== BF4PS PHASE 5A VEHICLE PAYLOAD INSPECTOR =====")
    print(
        f"soldier={SOLDIER_ID} persona={PERSONA_ID} "
        f"name={PLAYER_NAME!r} platform={PLATFORM} platformInt={p_int}"
    )
    print("database writes: 0")
    print("Battlelog requests: exactly 1")
    print(f"endpoint={url}")

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BF4PlayerStats/0.1 (+https://bf4playerstats.com)",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30.0) as response:
            status = getattr(response, "status", 200)
            body = response.read()
    except HTTPError as exc:
        print(f"HTTP ERROR status={exc.code}")
        return 2
    except (URLError, TimeoutError, OSError) as exc:
        print(f"TRANSPORT ERROR {exc.__class__.__name__}: {exc}")
        return 3

    print(f"http_status={status}")
    print(f"response_bytes={len(body)}")
    if status != 200:
        return 2

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"JSON ERROR {exc.__class__.__name__}: {exc}")
        return 4
    if not isinstance(payload, Mapping):
        print(f"root_type={_shape(payload)}")
        return 5

    _print_mapping("ROOT KEYS", payload)

    # Inspect the conventional data wrapper only when it actually exists and is
    # an object. We do not assume that vehicle rows live beneath it.
    data = payload.get("data")
    if isinstance(data, Mapping):
        _print_mapping("DATA KEYS", data)

    print("\n===== LIST CANDIDATES =====")
    candidates: list[tuple[str, list[Any]]] = []
    for prefix, mapping in (("root", payload), ("data", data)):
        if not isinstance(mapping, Mapping):
            continue
        for key, value in mapping.items():
            if isinstance(value, list):
                candidates.append((f"{prefix}.{key}", value))

    if not candidates:
        print("none")
    for path, rows in candidates:
        print(f"{path}: entries={len(rows)}")
        if rows and isinstance(rows[0], Mapping):
            first = rows[0]
            print(f"  first_entry_keys={sorted(first.keys())}")
            print("  first_entry_field_types:")
            for key in sorted(first):
                print(f"    {key}: {_shape(first[key])}")

            # Retention-field evidence only. Print values when those exact
            # Battlelog names are present; absence is evidence too.
            for key in ("guid", "name", "slug", "category", "kills", "timeIn", "destroyXinY"):
                if key in first:
                    print(f"  first_entry.{key}={first[key]!r}")

            null_fields = sorted(
                key for row in rows if isinstance(row, Mapping)
                for key, value in row.items() if value is None
            )
            print(f"  nullable_fields_seen={sorted(set(null_fields))}")

    print("\nPHASE 5A VEHICLE PAYLOAD INSPECTOR: COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
