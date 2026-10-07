from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step8_postrun_audit.py")


def test_step8_audit_parses():
    ast.parse(P.read_text())


def test_step8_audit_is_read_only_and_checks_frozen_evidence():
    s = P.read_text()
    assert "collection_attempt_started" in s
    assert "collection_success" in s and "collection_failure" in s
    assert "collection_persistence_failure" in s
    assert "battlelog_throttle" in s
    assert "rolling_1h_max_physical_starts" in s
    assert "observed_attempt_event_gap_min_seconds" in s
    assert "request_gate_spacing_note" in s
    assert "retry_gap_min_seconds" in s
    assert "remaining_cohort_jobs" in s
    assert "due_interval_mismatches" in s
    assert "database writes: 0" in s
    assert "Battlelog requests by audit: 0" in s
    upper = s.upper()
    assert " INSERT INTO " not in upper
    assert " UPDATE " not in upper
    assert " DELETE FROM " not in upper


def test_step8_uses_marker_frozen_cohort():
    s = P.read_text()
    assert "cohort_soldier_ids" in s
    assert "len(ids)!=1296" in s


def test_step8_accepts_only_exact_retry_displacement_at_ceiling():
    s = P.read_text()
    assert "retry_displacement_exact=(len(remaining)==retry_attempts)" in s
    assert "completed_or_displaced=(unique_jobs+len(remaining)==INITIAL_JOB_COUNT)" in s
    assert "len(pristine_remaining)==len(remaining)" in s
    assert "not unexplained_pristine" in s


def test_step8_does_not_treat_attempt_event_timestamp_as_exact_gate_clock():
    s = P.read_text()
    assert "observed_below_5" in s
    assert "observed_below_499" in s
    assert "and not spacing_bad" not in s
