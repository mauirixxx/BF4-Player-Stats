#!/usr/bin/env python3
"""Offline Phase 5B capacity calculator.

No database access and no Battlelog requests. Candidate populations/cadences
are explicit inputs derived from the accepted 2026-10-06 scheduling census.
"""
from __future__ import annotations

from dataclasses import dataclass

EGRESSES = 3
SECONDS_PER_REQUEST_PER_EGRESS = 5.0
THEORETICAL_REQUESTS_PER_DAY = int(EGRESSES * 86400 / SECONDS_PER_REQUEST_PER_EGRESS)
WEAPON_BYTES_MEAN = 585850.3
VEHICLE_BYTES_MEAN = 452844.3

# Mutually exclusive source-recency tiers from the accepted census.
SOURCE_TIERS = {
    "hot_lt_1h": 3939,
    "warm_1h_24h": 7844 + 13114,
    "recent_1d_7d": 47936,
    "cold_7d_plus": 80558 + 34973,
}


@dataclass(frozen=True)
class Cadence:
    detailed_hours: float | None
    weapons_hours: float | None
    vehicles_hours: float | None


def requests_per_day(population: int, hours: float | None) -> float:
    if hours is None:
        return 0.0
    if hours <= 0:
        raise ValueError("cadence hours must be positive or None")
    return population * 24.0 / hours


def evaluate(name: str, cadences: dict[str, Cadence]) -> None:
    by_resource = {"detailed": 0.0, "weapons": 0.0, "vehicles": 0.0}
    expensive_bytes = 0.0
    print(f"\n===== CANDIDATE: {name} =====")
    for tier, population in SOURCE_TIERS.items():
        cadence = cadences[tier]
        d = requests_per_day(population, cadence.detailed_hours)
        w = requests_per_day(population, cadence.weapons_hours)
        v = requests_per_day(population, cadence.vehicles_hours)
        by_resource["detailed"] += d
        by_resource["weapons"] += w
        by_resource["vehicles"] += v
        expensive_bytes += w * WEAPON_BYTES_MEAN + v * VEHICLE_BYTES_MEAN
        print(
            f"{tier:<16} population={population:>6} "
            f"detailed={d:>9.1f}/d weapons={w:>9.1f}/d vehicles={v:>9.1f}/d"
        )

    total = sum(by_resource.values())
    utilization = total / THEORETICAL_REQUESTS_PER_DAY * 100.0
    headroom = 100.0 - utilization
    print("resource totals:")
    for resource, value in by_resource.items():
        print(f"  {resource:<8} {value:>10.1f} requests/day")
    print(f"total requests/day={total:.1f}")
    print(f"theoretical three-egress ceiling={THEORETICAL_REQUESTS_PER_DAY} requests/day")
    print(f"theoretical utilization={utilization:.1f}%")
    print(f"theoretical headroom={headroom:.1f}%")
    print(f"measured weapon+vehicle response payload={expensive_bytes/1024/1024/1024:.2f} GiB/day")
    print("detailed response bytes: UNKNOWN / not included")


def main() -> int:
    print("===== BF4PS PHASE 5B OFFLINE CAPACITY CALCULATOR =====")
    print("database access: 0")
    print("Battlelog requests: 0")
    print(f"theoretical capacity={THEORETICAL_REQUESTS_PER_DAY} requests/day")
    print("source-recency tiers are observational proxies, NOT proven gameplay activity")

    # Deliberately contrasting starting points for discussion. These are model
    # candidates only; none is production policy.
    candidates = {
        "conservative-hot-set": {
            "hot_lt_1h": Cadence(1, 6, 6),
            "warm_1h_24h": Cadence(6, 24, 24),
            "recent_1d_7d": Cadence(24, 168, 168),
            "cold_7d_plus": Cadence(168, None, None),
        },
        "balanced-hot-set": {
            "hot_lt_1h": Cadence(1, 3, 3),
            "warm_1h_24h": Cadence(4, 12, 12),
            "recent_1d_7d": Cadence(24, 72, 72),
            "cold_7d_plus": Cadence(168, None, None),
        },
        "aggressive-hot-set": {
            "hot_lt_1h": Cadence(0.5, 2, 2),
            "warm_1h_24h": Cadence(2, 8, 8),
            "recent_1d_7d": Cadence(12, 48, 48),
            "cold_7d_plus": Cadence(168, None, None),
        },
    }
    for name, cadences in candidates.items():
        evaluate(name, cadences)

    print("\nNo candidate above is authorized production policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
