from pathlib import Path


SCRIPT = Path("scripts/phase5b_step6_launch_preflight.py")


def test_step6_launch_preflight_is_read_only_and_network_free():
    source = SCRIPT.read_text()
    assert "engine.connect()" in source
    assert "engine.begin()" not in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source
    assert "collect_one_" not in source
    assert "fetch_detailed_stats" not in source
    assert "fetch_weapon_stats" not in source
    assert "fetch_vehicle_stats" not in source
    assert "Battlelog requests: 0" in source


def test_step6_launch_preflight_checks_pristine_queue_and_registry():
    source = SCRIPT.read_text()
    assert "expected 27 Step 6 jobs" in source
    assert "attempt_count" in source
    assert "foreign background jobs present" in source
    assert "collection_attempt_started" in source
    assert "expected zero physical attempts after marker" in source
    assert "collector identity drift" in source
    assert "is disabled" in source
    assert "is drained" in source
    assert "already owns current_job_id" in source
