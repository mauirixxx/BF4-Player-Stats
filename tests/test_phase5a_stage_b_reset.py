from pathlib import Path


def test_stage_b_reset_preserves_probe_history_and_weapon_data():
    source=Path("scripts/phase5a_stage_b_reset_run1.py").read_text()
    assert "PROBE_BOUNDARY_EVENT_ID" in source
    assert "DELETE FROM soldier_vehicle_stats" in source
    assert "DELETE FROM collection_events" not in source
    assert "DELETE FROM soldier_weapon_stats" not in source
    assert "weapons_state" in source


def test_stage_b_reset_only_resets_probe_soldier_vehicle_state():
    source=Path("scripts/phase5a_stage_b_reset_run1.py").read_text()
    assert "WHERE soldier_id=:soldier_id" in source
    assert "vehicles_state='never_attempted'" in source
    assert "deleted.rowcount == 82" in source


def test_stage_b_reset_creates_new_durable_run_boundary():
    source=Path("scripts/phase5a_stage_b_reset_run1.py").read_text()
    assert "phase5a_stage_b_run_started" not in source  # imported constant, not duplicated
    assert "RUN_MARKER_EVENT_TYPE" in source
    assert "'max_physical_attempts',:ceiling" in source


def test_stage_b_preflight_is_read_only_and_requires_pristine_30():
    source=Path("scripts/phase5a_stage_b_preflight.py").read_text()
    assert "database writes: 0" in source
    assert "Battlelog requests: 0" in source
    assert "all vehicle collection states are pristine" in source
    assert "Stage A weapon persistence remains for all 30" in source
    assert "no Stage B run attempts after boundary" in source
