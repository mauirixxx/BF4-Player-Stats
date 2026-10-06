from pathlib import Path

SCRIPT = Path("scripts/phase5b_scheduling_census.py").read_text()


def test_census_is_read_only_and_network_free():
    lowered = SCRIPT.lower()
    assert "database writes: 0" in SCRIPT
    assert "Battlelog requests: 0" in SCRIPT
    for token in ("insert into", "update collection_", "delete from", "requests.", "httpx.", "urllib.request"):
        assert token not in lowered


def test_census_uses_documented_resource_prefixed_state_columns():
    for resource in ("detailed", "profile", "weapons", "vehicles"):
        assert f"{resource}_state" in SCRIPT
        assert f"{resource}_last_success_at" in SCRIPT
        assert f"{resource}_consecutive_failures" in SCRIPT
        assert f"{resource}_last_error_class" in SCRIPT
    assert "collection_state WHERE resource" not in SCRIPT


def test_census_reports_queue_collectors_gates_and_durable_attempts():
    assert "FROM collection_jobs" in SCRIPT
    assert "FROM collectors" in SCRIPT
    assert "FROM request_gates" in SCRIPT
    assert "event_type='collection_attempt_started'" in SCRIPT


def test_source_recency_is_not_mislabeled_as_gameplay_activity():
    assert "source recency is discovery/source observation, NOT proven gameplay activity" in SCRIPT
    assert "FROM soldier_sources" in SCRIPT


def test_census_fences_test_database_and_schema_revision():
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in SCRIPT
    assert 'EXPECTED_REVISION = "0003_request_gates"' in SCRIPT
    assert "SELECT current_database()" in SCRIPT
    assert "SELECT version_num FROM alembic_version" in SCRIPT
