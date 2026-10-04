"""Read-only live validation of the Phase 1 Battlelog detailed-stat boundary.

This harness performs exactly one Battlelog detailed-statistics request and
normalizes the response. It deliberately does not connect to BF4PS PostgreSQL,
claim a collection job, or persist the Battlelog payload/statistics.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from bf4ps.battlelog_detailed import fetch_detailed_stats, normalize_detailed_stats

PERSONA_ID = 236753552
PLATFORM = "pc"
PLAYER_NAME = "mauirixxx"


def display_value(value: int | Decimal | None) -> str:
    if value is None:
        return "NULL"
    return str(value)


def main() -> None:
    print("===== BF4PS PHASE 1 LIVE DETAILED FETCH =====")
    print()
    print("READ-ONLY VALIDATION")
    print("No BF4PS database connection or writes are performed by this script.")
    print()
    print(f"player:     {PLAYER_NAME}")
    print(f"persona_id: {PERSONA_ID}")
    print(f"platform:   {PLATFORM}")
    print()
    print("Issuing one Battlelog detailed-statistics request...")

    result = fetch_detailed_stats(PERSONA_ID, PLATFORM)

    print("HTTP fetch: PASS")
    print(f"platformInt: {result.platform_int}")
    print(f"payload root keys: {', '.join(sorted(result.payload.keys()))}")

    data = result.payload.get("data")
    if isinstance(data, Mapping):
        print(f"data keys: {', '.join(sorted(data.keys()))}")
        general = data.get("generalStats")
    else:
        general = result.payload.get("generalStats")

    if isinstance(general, Mapping):
        print(f"generalStats source fields: {len(general)}")
    else:
        print("generalStats source fields: unavailable")

    normalized = normalize_detailed_stats(
        result.payload,
        expected_persona_id=PERSONA_ID,
        expected_platform_int=result.platform_int,
    )

    present = sum(value is not None for value in normalized.values())
    missing = len(normalized) - present

    print()
    print("===== NORMALIZED DETAILED STATS =====")
    print(f"retained fields: {len(normalized)}")
    print(f"present:         {present}")
    print(f"missing/null:    {missing}")
    print()

    for field, value in normalized.items():
        print(f"{field:28} {display_value(value)}")

    print()
    print("PHASE 1 LIVE DETAILED FETCH: PASS")


if __name__ == "__main__":
    main()
