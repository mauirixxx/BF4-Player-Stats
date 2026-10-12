"""Generate a transaction-guarded D4-only SQL import from the frozen manifest.

Offline generator: does not connect to PostgreSQL or send HTTP. SQL must be
executed by an operator on the intended D4 PostgreSQL primary only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SHA = "7bd0ed22ba19f2f7e8d4b6acf9c0c113115a50a9e8f5bc74a6caab5b64e215d2"
DB = "bf4ps_scratch_stage9c_d4"
REV = "0006_stage9c_soak_round_ledger"


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def generate(manifest: Path) -> str:
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA:
        raise ValueError("frozen manifest SHA256 mismatch")
    rows = json.loads(raw)["rows"]
    if len(rows) != 300 or len({(r["platform"], r["persona_id"]) for r in rows}) != 300:
        raise ValueError("invalid manifest identities")
    for row in rows:
        if row["site"] not in ("tcou", "kah-01", "hnl-01") or row["platform"] not in ("pc", "ps4", "xboxone"):
            raise ValueError("invalid manifest site or platform")
        if type(row["persona_id"]) is not int or row["persona_id"] <= 0 or not isinstance(row["name"], str) or not row["name"].strip():
            raise ValueError("invalid persona/name")
    values = ",\n".join(
        f"({int(r['persona_id'])}, {quote(r['platform'])}, {quote(r['name'])})"
        for r in rows
    )
    return f"""\\set ON_ERROR_STOP on
BEGIN;
DO $guard$
BEGIN
  IF current_database() <> '{DB}'
    OR (SELECT version_num FROM alembic_version) <> '{REV}'
    OR (SELECT count(*) FROM soldiers) <> 0
    OR (SELECT count(*) FROM collection_state) <> 0
    OR (SELECT count(*) FROM collection_jobs) <> 0
    OR (SELECT count(*) FROM collection_events) <> 0
    OR (SELECT count(*) FROM collectors) <> 0
    OR (SELECT count(*) FROM soak_runs) <> 0
  THEN
    RAISE EXCEPTION 'D4 pristine schema guard failed';
  END IF;
END
$guard$;
CREATE TEMP TABLE d4_manifest(persona_id bigint, platform text, current_name text) ON COMMIT DROP;
INSERT INTO d4_manifest(persona_id,platform,current_name) VALUES
{values};
DO $validate$
BEGIN
  IF (SELECT count(*) FROM d4_manifest) <> 300
    OR (SELECT count(DISTINCT (platform,persona_id)) FROM d4_manifest) <> 300
    OR (SELECT count(*) FROM d4_manifest WHERE platform='pc') <> 100
    OR (SELECT count(*) FROM d4_manifest WHERE platform='ps4') <> 100
    OR (SELECT count(*) FROM d4_manifest WHERE platform='xboxone') <> 100
  THEN
    RAISE EXCEPTION 'D4 manifest SQL validation failed';
  END IF;
END
$validate$;
INSERT INTO soldiers(persona_id,platform,current_name,first_seen_at,last_seen_at)
SELECT persona_id,platform,current_name,now(),now() FROM d4_manifest ORDER BY platform,persona_id;
INSERT INTO collection_state(soldier_id)
SELECT soldier_id FROM soldiers;
DO $final$
BEGIN
  IF (SELECT count(*) FROM soldiers) <> 300
    OR (SELECT count(*) FROM collection_state) <> 300
    OR (SELECT count(*) FROM collection_jobs) <> 0
    OR (SELECT count(*) FROM collection_events) <> 0
  THEN
    RAISE EXCEPTION 'D4 import reconciliation failed';
  END IF;
END
$final$;
COMMIT;
"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.write_text(generate(args.manifest))
    print(json.dumps({"sql_path": str(args.output), "manifest_sha256": EXPECTED_SHA, "identities": 300, "database": DB, "executed": False}))


if __name__ == "__main__":
    main()
