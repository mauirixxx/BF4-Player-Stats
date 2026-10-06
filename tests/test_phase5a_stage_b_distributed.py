from pathlib import Path


def test_stage_b_seed_is_vehicle_only_and_30_bounded():
    s=Path("scripts/phase5a_stage_b_seed.py").read_text()
    assert 'resource="vehicles"' in s
    assert "GLOBAL_ATTEMPT_CEILING" in s
    assert "Battlelog requests: 0" in s


def test_stage_b_worker_uses_vehicle_collector_and_run_boundary():
    s=Path("scripts/phase5a_stage_b_worker.py").read_text()
    assert "collect_one_vehicle_job" in s
    assert "attempts_after_event_id=run_start_event_id" in s
    assert "max_total_attempts=GLOBAL_ATTEMPT_CEILING" in s
    assert "resource='vehicles'" in s
    assert "THROTTLE SIGNAL; stopping" in s


def test_stage_b_worker_rejects_foreign_background_work():
    s=Path("scripts/phase5a_stage_b_worker.py").read_text()
    assert "foreign background" not in s or "foreign=" in s
    assert "NOT (resource='vehicles' AND soldier_id=ANY(:ids))" in s


def test_stage_b_audit_requires_physical_terminal_reconciliation():
    s=Path("scripts/phase5a_stage_b_audit.py").read_text()
    assert "exactly 30 durable physical vehicle attempts exist" in s
    assert "every physical attempt has exactly one durable terminal outcome" in s
    assert "all three frozen collectors participated in physical attempts" in s
    assert "no persistence-layer failure evidence" in s
    assert "event platform split is exactly 10/10/10" in s


def test_stage_b_audit_reads_vehicle_persistence_only():
    s=Path("scripts/phase5a_stage_b_audit.py").read_text()
    assert "soldier_vehicle_stats" in s
    assert "vehicles_state" in s
    assert "metadata" in s and "vehicle_rows" in s
