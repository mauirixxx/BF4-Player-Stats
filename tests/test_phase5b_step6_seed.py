from pathlib import Path


def test_step6_seed_is_exactly_bounded_and_does_not_collect():
    source = Path("scripts/phase5b_step6_seed.py").read_text()
    assert "RUN_MARKER_EVENT_TYPE" in source
    assert "GLOBAL_ATTEMPT_CEILING" in source
    assert "for resource in RESOURCES" in source
    assert "enqueue_job(" in source
    assert "foreign background jobs exist" in source
    assert "collection_attempt_started" not in source
    assert "collect_one_" not in source
    assert "Battlelog requests: 0" in source


def test_step6_seed_audit_is_read_only_and_requires_zero_attempts():
    source = Path("scripts/phase5b_step6_seed_audit.py").read_text()
    assert "collection_attempt_started" in source
    assert "attempts == 0" in source
    assert "GLOBAL_ATTEMPT_CEILING" in source
    for token in ("INSERT ", "UPDATE ", "DELETE ", "enqueue_job(", "collect_one_"):
        assert token not in source
