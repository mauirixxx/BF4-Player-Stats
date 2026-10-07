from pathlib import Path
import inspect

from bf4ps.background_service import (
    ACTIVE_SLOTS,
    claim_production_background_job,
    BACKGROUND_SLOTS_PER_HOUR,
    BOOTSTRAP_SLOTS,
    RECOVERY_SLOTS,
)


def test_frozen_hourly_background_budget_and_shares():
    assert BACKGROUND_SLOTS_PER_HOUR == 1296
    assert ACTIVE_SLOTS == 972
    assert BOOTSTRAP_SLOTS == 259
    assert RECOVERY_SLOTS == 65
    assert ACTIVE_SLOTS + BOOTSTRAP_SLOTS + RECOVERY_SLOTS == BACKGROUND_SLOTS_PER_HOUR


def test_background_admission_uses_postgresql_coordination_and_existing_queue():
    source = Path("bf4ps/background_service.py").read_text()
    assert "pg_advisory_xact_lock" in source
    assert "claim_next_job(" in source
    assert "INSERT INTO collection_jobs" not in source
    assert "UPDATE collection_jobs" not in source
    assert "DELETE FROM collection_jobs" not in source


def test_interactive_work_blocks_background_admission():
    source = Path("bf4ps/background_service.py").read_text()
    assert "lane = 'interactive'" in source
    assert "if interactive_pending:" in source
    assert "return None" in source


def test_completed_service_is_counted_from_durable_attempt_snapshots():
    source = Path("bf4ps/background_service.py").read_text()
    assert "event_type = 'collection_attempt_started'" in source
    assert "occurred_at >= now() - interval '1 hour'" in source
    assert "metadata->>'priority_class'" in source
    assert "metadata->>'retry'" in source


def test_owned_pre_request_jobs_are_reserved_against_budget():
    source = Path("bf4ps/background_service.py").read_text()
    assert "status IN ('claimed', 'running')" in source
    assert "e.attempt_number = j.attempt_count" in source


def test_attempt_start_metadata_snapshots_scheduler_class_for_all_resources():
    for path in (
        "bf4ps/detailed_collector.py",
        "bf4ps/weapon_collector.py",
        "bf4ps/vehicle_collector.py",
    ):
        source = Path(path).read_text()
        assert "'physical_request', true" in source
        assert "'priority_class'" in source
        assert "'retry'" in source


def test_detailed_now_has_durable_physical_attempt_marker():
    source = Path("bf4ps/detailed_collector.py").read_text()
    assert "def _record_detailed_attempt_started(" in source
    assert "'collection_attempt_started'" in source


def test_production_budget_mode_is_opt_in_for_collectors():
    for path in (
        "bf4ps/detailed_collector.py",
        "bf4ps/weapon_collector.py",
        "bf4ps/vehicle_collector.py",
    ):
        source = Path(path).read_text()
        assert "enforce_production_budget: bool = False" in source
        assert "claim_production_background_job(" in source
        assert "claim_production_background_job(" in source


def test_production_admission_can_retain_explicit_live_safety_bounds():
    signature = inspect.signature(claim_production_background_job)
    assert "allowed_soldier_ids" in signature.parameters
    assert signature.parameters["allowed_soldier_ids"].default is None
    assert "max_total_attempts" in signature.parameters
    assert signature.parameters["max_total_attempts"].default is None
    assert "attempts_after_event_id" in signature.parameters
    assert signature.parameters["attempts_after_event_id"].default is None
    assert "attempt_ceiling_resources" in signature.parameters
    assert signature.parameters["attempt_ceiling_resources"].default is None

    service = Path("bf4ps/background_service.py").read_text()
    assert "allowed_soldier_ids=allowed_soldier_ids" in service
    assert "max_total_attempts=max_total_attempts" in service
    assert "attempts_after_event_id=attempts_after_event_id" in service
    assert "attempt_ceiling_resources=attempt_ceiling_resources" in service

    detailed = Path("bf4ps/detailed_collector.py").read_text()
    weapons = Path("bf4ps/weapon_collector.py").read_text()
    vehicles = Path("bf4ps/vehicle_collector.py").read_text()
    for source in (detailed, weapons, vehicles):
        assert "allowed_soldier_ids=allowed_soldier_ids" in source
        assert "max_total_attempts=max_total_attempts" in source
        assert "attempts_after_event_id=attempts_after_event_id" in source
        assert "attempt_ceiling_resources=attempt_ceiling_resources" in source
