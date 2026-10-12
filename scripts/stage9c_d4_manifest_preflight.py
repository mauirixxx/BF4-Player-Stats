"""Offline validation of the frozen 300-persona D4 candidate manifest.

No database connection, no Battlelog HTTP, no queue writes.
Run: python -m scripts.stage9c_d4_manifest_preflight
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "docs" / "stage9c-d3-real-300-candidate-manifest-2026-10-11.json"
SITES = ("tcou", "kah-01", "hnl-01")
PLATFORMS = ("pc", "ps4", "xboxone")


def validate(path: Path) -> dict:
    raw = path.read_bytes()
    data = json.loads(raw)
    if data.get("status") != "READ_ONLY_CANDIDATES_UNVALIDATED_IN_TARGET":
        raise ValueError("unexpected manifest status")
    rows = data.get("rows")
    if not isinstance(rows, list) or len(rows) != 300:
        raise ValueError("expected exactly 300 candidate rows")
    pairs = set()
    site_counts = Counter()
    platform_counts = Counter()
    site_platform = Counter()
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"source_soldier_id", "persona_id", "name", "platform", "site"}:
            raise ValueError(f"invalid fields in row {i}")
        if type(row["persona_id"]) is not int or row["persona_id"] <= 0:
            raise ValueError(f"invalid persona_id in row {i}")
        if type(row["source_soldier_id"]) is not int or row["source_soldier_id"] <= 0:
            raise ValueError(f"invalid historical soldier_id in row {i}")
        if not isinstance(row["name"], str) or not row["name"].strip():
            raise ValueError(f"invalid name in row {i}")
        site, platform = row["site"], row["platform"]
        if site not in SITES or platform not in PLATFORMS:
            raise ValueError(f"invalid site/platform in row {i}")
        key = (platform, row["persona_id"])
        if key in pairs:
            raise ValueError(f"duplicate platform/persona identity in row {i}")
        pairs.add(key)
        site_counts[site] += 1
        platform_counts[platform] += 1
        site_platform[(site, platform)] += 1
    if any(site_counts[s] != 100 for s in SITES):
        raise ValueError("site allocation is not 100/100/100")
    if any(platform_counts[p] != 100 for p in PLATFORMS):
        raise ValueError("platform allocation is not 100/100/100")
    return {
        "passed": True,
        "http_requests": 0,
        "database_writes": 0,
        "candidate_count": len(rows),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "site_counts": dict(site_counts),
        "platform_counts": dict(platform_counts),
        "site_platform_counts": {f"{s}/{p}": site_platform[(s, p)] for s in SITES for p in PLATFORMS},
        "target_database_validated": False,
        "http_ignition_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    print(json.dumps(validate(args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
