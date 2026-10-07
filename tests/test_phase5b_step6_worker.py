from pathlib import Path

from bf4ps.phase5b_step6_cohort import GLOBAL_ATTEMPT_CEILING, HOSTS, RESOURCES, SOLDIER_IDS


WORKER = Path("scripts/phase5b_step6_worker.py")


def test_step6_worker_frozen_bounds():
    assert GLOBAL_ATTEMPT_CEILING == 27
    assert len(SOLDIER_IDS) == 9
    assert RESOURCES == ("detailed", "weapons", "vehicles")
    assert set(HOSTS) == {"hnl-01", "kah-01", "tcou"}


def test_step6_worker_uses_marker_scoped_aggregate_production_claims():
    source = WORKER.read_text()
    assert "attempts_after_event_id=boundary" in source
    assert "attempt_ceiling_resources=RESOURCES" in source
    assert "max_total_attempts=GLOBAL_ATTEMPT_CEILING" in source
    assert "allowed_soldier_ids=SOLDIER_IDS" in source
    assert "enforce_production_budget=True" in source
    assert "REQUEST_INTERVAL_SECONDS" in source


def test_step6_worker_calls_all_three_retained_collectors():
    source = WORKER.read_text()
    assert "collect_one_detailed_job(" in source
    assert "collect_one_weapon_job(" in source
    assert "collect_one_vehicle_job(" in source


def test_step6_worker_safety_uses_physical_starts_and_abort_signals():
    source = WORKER.read_text()
    assert "event_type = 'collection_attempt_started'" in source
    assert "GROUP BY job_id, attempt_number" in source
    assert "http_status IN (403, 429)" in source
    assert "collection_persistence_failure" in source
    assert "attempts > GLOBAL_ATTEMPT_CEILING" in source


def test_step6_worker_does_not_activate_discovery_or_materializer():
    source = WORKER.read_text()
    assert "discovery_service" not in source
    assert "materialize_production_jobs" not in source
    assert "materialize_bf4sw_observation" not in source
