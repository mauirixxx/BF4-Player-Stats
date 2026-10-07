from __future__ import annotations
import ast
from pathlib import Path

P=Path("scripts/phase5b_step8_postrun_audit.py")

def test_step8_audit_parses():
    ast.parse(P.read_text())

def test_step8_audit_is_read_only_and_checks_frozen_evidence():
    s=P.read_text()
    assert "collection_attempt_started" in s
    assert "collection_success" in s and "collection_failure" in s
    assert "collection_persistence_failure" in s
    assert "battlelog_throttle" in s
    assert "rolling_1h_max_physical_starts" in s
    assert "per_egress_spacing_violations_lt_5s" in s
    assert "retry_gap_min_seconds" in s
    assert "remaining_cohort_jobs" in s
    assert "due_interval_mismatches" in s
    assert "database writes: 0" in s
    assert "Battlelog requests by audit: 0" in s
    upper=s.upper()
    assert " INSERT INTO " not in upper
    assert " UPDATE " not in upper
    assert " DELETE FROM " not in upper

def test_step8_uses_marker_frozen_cohort():
    s=P.read_text()
    assert 'cohort_soldier_ids' in s
    assert "len(ids)!=1296" in s
