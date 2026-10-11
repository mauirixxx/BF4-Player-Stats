"""Read-only preflight for a bounded BF4PS live batch manifest.

Usage:
  python -m scripts.stage9c_batch_preflight --manifest /path/cohort.json

Manifest v1:
  {"version":1,"soldiers":[{"platform":"pc","persona_id":236753552}],
   "resources":["detailed","weapons","vehicles"],"max_attempts":3}
No HTTP, DB mutations, or secret output. Missing soldiers are reported, not inserted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

EXPECTED_DB = "bf4ps_scratch_stage9c_integration"
EXPECTED_ROLE = "bf4ps_stage9c_integration"
EXPECTED_REVISION = "0004_stage9c_supervision_runs"
RESOURCES = frozenset({"detailed", "weapons", "vehicles"})
PLATFORMS = frozenset({"pc", "ps4", "xboxone"})


def parse_manifest(raw: dict) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...], int]:
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("manifest version must be 1")
    entries = raw.get("soldiers")
    resources = raw.get("resources")
    limit = raw.get("max_attempts")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise ValueError("soldiers must contain 1-100 entries")
    if not isinstance(resources, list) or not 1 <= len(resources) <= 3:
        raise ValueError("resources must contain 1-3 entries")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 300:
        raise ValueError("max_attempts must be an integer between 1 and 300")
    normalized_resources = tuple(resources)
    if len(set(normalized_resources)) != len(normalized_resources) or not set(normalized_resources) <= RESOURCES:
        raise ValueError("duplicate or unsupported resources")
    soldiers = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("soldier entry must be an object")
        platform, persona = entry.get("platform"), entry.get("persona_id")
        if platform not in PLATFORMS or not isinstance(persona, int) or isinstance(persona, bool) or persona <= 0:
            raise ValueError("invalid platform or persona_id")
        soldiers.append((platform, persona))
    if len(set(soldiers)) != len(soldiers):
        raise ValueError("duplicate soldier identity")
    if limit > len(soldiers) * len(normalized_resources):
        raise ValueError("attempt ceiling exceeds number of soldier/resource combinations")
    return tuple(soldiers), normalized_resources, limit


def preflight(manifest_path: Path) -> None:
    soldiers, resources, limit = parse_manifest(json.loads(manifest_path.read_text()))
    engine = create_engine(os.environ["BF4PS_STAGE9C_INTEGRATION_URL"], pool_pre_ping=True)
    with engine.connect() as conn:
        identity = conn.execute(text(
            "SELECT current_database(),current_user,pg_is_in_recovery(),"
            "current_setting('transaction_read_only')"
        )).one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if tuple(identity) != (EXPECTED_DB, EXPECTED_ROLE, False, "off") or revision != EXPECTED_REVISION:
            raise RuntimeError("refusing unexpected database, role, primary state or revision")
        collectors = conn.execute(text("""
            SELECT collector_name,hostname,egress_key,lane,enabled,drained,retired_at,current_job_id
            FROM collectors
        """)).mappings().all()
        if len(collectors) != 1 or not (
            collectors[0]["collector_name"] == "live-persistence-validation-tcou"
            and collectors[0]["hostname"] == "tcou"
            and collectors[0]["egress_key"] == "tcou-live-validation"
            and collectors[0]["lane"] == "background"
            and collectors[0]["enabled"] and not collectors[0]["drained"]
            and collectors[0]["retired_at"] is None
            and collectors[0]["current_job_id"] is None
        ):
            raise RuntimeError("refusing unexpected collector state")
        queue_count = conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()
        print(f"TARGET db={EXPECTED_DB} revision={revision} queue={queue_count}")
        print(f"MANIFEST soldiers={len(soldiers)} resources={','.join(resources)} max_attempts={limit}")
        for platform, persona in soldiers:
            row = conn.execute(text("""
                SELECT s.soldier_id,cs.detailed_state,cs.weapons_state,cs.vehicles_state
                FROM soldiers s LEFT JOIN collection_state cs USING(soldier_id)
                WHERE s.platform=:platform AND s.persona_id=:persona
            """), {"platform": platform, "persona": persona}).mappings().one_or_none()
            if row is None:
                print(f"IDENTITY {platform}/{persona}: MISSING (init required)")
                continue
            states = {resource: row[resource + "_state"] for resource in resources}
            print(f"IDENTITY {platform}/{persona}: soldier_id={row['soldier_id']} states={states}")
        if queue_count:
            print("WARNING existing queue is nonempty; run command must refuse conflicting work")
    print("READ-ONLY PREFLIGHT COMPLETE — no jobs queued and no HTTP issued")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    preflight(args.manifest)


if __name__ == "__main__":
    main()
