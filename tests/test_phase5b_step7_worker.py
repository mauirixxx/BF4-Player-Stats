import ast
from pathlib import Path
P=Path("scripts/phase5b_step7_worker.py")
def test_worker_parses_and_preserves_live_safety_contract():
 s=P.read_text(); ast.parse(s,filename=str(P))
 for x in ("allowed_soldier_ids=ids","max_total_attempts=GLOBAL_ATTEMPT_CEILING",
  "attempts_after_event_id=boundary","attempt_ceiling_resources=RESOURCES",
  "enforce_production_budget=True","REQUEST_INTERVAL_SECONDS",
  "collection_persistence_failure","http_status IN (403,429)","battlelog_throttle"):
  assert x in s
def test_worker_uses_marker_allowlist_and_common_time_boundary():
 s=P.read_text()
 assert 'meta["cohort_soldier_ids"]' in s
 assert "started_at>:marker_at" in s
 assert "started+DURATION" in s
 assert "SELECT now()" in s
 assert "3-hour endurance deadline reached" in s
def test_worker_does_not_activate_discovery_materializer():
 s=P.read_text()
 assert "discovery_service" not in s
 assert "materialize_production_jobs" not in s
