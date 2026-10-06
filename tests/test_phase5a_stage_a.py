from pathlib import Path

def test_phase5a_stage_a_common_locks_experiment_boundaries():
    source = Path("scripts/phase5a_stage_a_common.py").read_text(encoding="utf-8")
    assert "GLOBAL_ATTEMPT_CEILING = 30" in source
    assert "REQUEST_INTERVAL_SECONDS = 5.0" in source
    assert "RETRY_AFTER_SECONDS = 86400" in source
    assert '"hnl-01"' in source and '"kah-01"' in source and '"tcou"' in source
    assert "FROZEN_COHORT" in source

def test_phase5a_stage_a_worker_is_weapons_only_and_bounded():
    source = Path("scripts/phase5a_stage_a_worker.py").read_text(encoding="utf-8")
    assert "collect_one_weapon_job" in source
    assert "collect_one_detailed_job" not in source
    assert "collect_one_vehicle" not in source
    assert "allowed_soldier_ids=SOLDIER_IDS" in source
    assert "max_total_attempts=GLOBAL_ATTEMPT_CEILING" in source
    assert "retry_after_seconds=RETRY_AFTER_SECONDS" in source
    assert "http_status in {403, 429}" in source

def test_phase5a_stage_a_seed_only_creates_weapon_jobs():
    source = Path("scripts/phase5a_stage_a_seed.py").read_text(encoding="utf-8")
    assert 'resource="weapons"' in source
    assert "FROZEN_COHORT" in source
    assert "enqueue_job" in source
    assert 'resource="vehicles"' not in source

def test_phase5a_stage_a_audit_is_read_only():
    source = Path("scripts/phase5a_stage_a_audit.py").read_text(encoding="utf-8")
    assert "engine.connect()" in source
    assert "engine.begin()" not in source
    upper = source.upper()
    assert "INSERT INTO" not in upper
    assert "UPDATE COLLECTION" not in upper
    assert "DELETE FROM" not in upper


def test_phase5a_stage_a_worker_does_not_invent_database_hostname_contract():
    common = Path("scripts/phase5a_stage_a_common.py").read_text(encoding="utf-8")
    worker = Path("scripts/phase5a_stage_a_worker.py").read_text(encoding="utf-8")
    assert "EXPECTED_DB_HOST" not in common
    assert "EXPECTED_DB_HOST" not in worker
    assert "parsed.hostname" not in worker
    assert 'parsed.path.lstrip("/") != EXPECTED_DATABASE' in worker
    assert "assert_target(conn)" in worker
