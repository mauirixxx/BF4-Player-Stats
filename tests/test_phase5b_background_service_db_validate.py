from pathlib import Path


def _source() -> str:
    return Path("scripts/phase5b_background_service_db_validate.py").read_text()


def test_harness_is_test_database_and_revision_fenced():
    source = _source()
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in source
    assert 'EXPECTED_REVISION = "0003_request_gates"' in source
    assert "SELECT current_database()" in source
    assert "SELECT version_num FROM alembic_version" in source


def test_harness_requires_explicit_existing_idle_soldiers():
    source = _source()
    assert 'action="append"' in source
    assert "exactly four distinct positive --soldier-id values" in source
    assert "status IN ('claimed', 'running')" in source


def test_harness_is_rollback_only_and_has_no_battlelog_runtime():
    source = _source()
    assert "tx.rollback()" in source
    assert ".commit(" not in source
    assert "fetch_detailed_stats" not in source
    assert "fetch_weapon" not in source
    assert "fetch_vehicle" not in source
    assert "requests." not in source
    assert "httpx." not in source


def test_harness_exercises_frozen_background_policy():
    source = _source()
    assert "interactive precedence" in source
    assert "BOOTSTRAP_SLOTS" in source
    assert "RECOVERY_SLOTS" in source
    assert "BACKGROUND_SLOTS_PER_HOUR" in source
    assert "unused reservation borrowing" in source
    assert "claim_production_background_job(" in source


def test_synthetic_usage_parameters_have_explicit_postgresql_types():
    source = _source()
    assert "CAST(:priority_class AS text)" in source
    assert "CAST(:retry AS boolean)" in source
    assert "CAST(:count AS integer)" in source
