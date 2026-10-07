from pathlib import Path


def test_step6_preflight_is_read_only_and_fenced():
    source = Path("scripts/phase5b_step6_preflight.py").read_text()
    assert "SELECT current_database()" in source
    assert "SELECT version_num FROM alembic_version" in source
    assert "SELECT pg_is_in_recovery()" in source
    assert "transaction_read_only" in source
    assert "COHORT" in source
    assert "RUN_MARKER_EVENT_TYPE" in source
    for token in ("INSERT ", "UPDATE ", "DELETE ", "enqueue_job(", "collect_one_"):
        assert token not in source
    assert "Battlelog requests: 0" in source
    assert "database writes: 0" in source
