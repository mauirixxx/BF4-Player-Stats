from pathlib import Path


def test_stage_b_probe_is_hard_bounded_to_one_soldier_and_attempt():
    source = Path("scripts/phase5a_stage_b_vehicle_probe.py").read_text(encoding="utf-8")
    assert "SOLDIER_ID = 15" in source
    assert "max_total_attempts=1" in source
    assert "allowed_soldier_ids=(SOLDIER_ID,)" in source
    assert "attempts_after_event_id=int(marker)" in source


def test_stage_b_probe_requires_pristine_vehicle_state_and_preserves_weapons():
    source = Path("scripts/phase5a_stage_b_vehicle_probe.py").read_text(encoding="utf-8")
    assert '"never_attempted"' in source
    assert "soldier_vehicle_stats" in source
    assert "state[\"weapons_state\"] != \"success\"" in source
    assert "soldier_weapon_stats" in source


def test_stage_b_probe_requires_empty_background_queue():
    source = Path("scripts/phase5a_stage_b_vehicle_probe.py").read_text(encoding="utf-8")
    assert "SELECT count(*) FROM collection_jobs" in source
    assert "WHERE lane='background'" in source
    assert "background queue is not empty" in source


def test_stage_b_probe_audit_is_read_only_and_reconciles_attempt():
    source = Path("scripts/phase5a_stage_b_vehicle_probe_audit.py").read_text(encoding="utf-8")
    assert "database writes: 0" in source
    assert "Battlelog requests: 0" in source
    assert "collection_attempt_started" in source
    assert "collection_persistence_failure" in source
    assert "physical attempt reconciles to terminal event" in source
