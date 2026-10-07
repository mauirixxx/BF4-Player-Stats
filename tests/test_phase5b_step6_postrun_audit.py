from pathlib import Path

SCRIPT=Path("scripts/phase5b_step6_postrun_audit.py")

def test_postrun_audit_is_read_only_and_network_free():
    s=SCRIPT.read_text()
    assert "engine.connect()" in s
    assert "engine.begin()" not in s
    assert "INSERT " not in s and "UPDATE " not in s and "DELETE " not in s
    assert "collect_one_" not in s and "fetch_" not in s
    assert "Battlelog requests by audit: 0" in s

def test_postrun_audit_reconciles_step6_contract():
    s=SCRIPT.read_text()
    for needle in (
        "collection_attempt_started","collection_success","collection_failure",
        "collection_persistence_failure","http_status IN (403,429)",
        "foreign_physical_starts_by_step6_collectors","remaining_cohort_jobs",
        "non_success_or_failure_debt_states","due_interval_mismatches",
        "dict(by_resource)=={r:9 for r in RESOURCES}",
        '"pc":9,"ps4":9,"xboxone":9',
    ):
        assert needle in s
