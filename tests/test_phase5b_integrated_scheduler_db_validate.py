from pathlib import Path


def _source() -> str:
    return Path("scripts/phase5b_integrated_scheduler_db_validate.py").read_text()


def test_step5_harness_is_test_database_revision_and_rollback_fenced():
    source = _source()
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in source
    assert 'EXPECTED_REVISION = "0003_request_gates"' in source
    assert "SELECT current_database()" in source
    assert "SELECT version_num FROM alembic_version" in source
    assert "tx.rollback()" in source
    assert ".commit(" not in source


def test_step5_harness_uses_production_scheduler_and_persistence_paths():
    source = _source()
    assert "materialize_bf4sw_observation(" in source
    assert "claim_production_background_job(" in source
    assert "mark_job_running(" in source
    assert "retry_delay_for_failure(" in source
    assert "persist_detailed_retry_failure(" in source
    assert "persist_detailed_success(" in source


def test_step5_harness_has_no_battlelog_request_runtime():
    source = _source()
    assert "fetch_detailed_stats" not in source
    assert "requests." not in source
    assert "httpx." not in source


def test_step5_harness_proves_retry_and_resource_isolation():
    source = _source()
    assert "retry_seconds == 900" in source
    assert "replay.created_resources == ()" in source
    assert "retry_job.attempt_count == 2" in source
    assert 'final_state["detailed_consecutive_failures"] == 0' in source
    assert "weapons/vehicles state isolation: PASS" in source
