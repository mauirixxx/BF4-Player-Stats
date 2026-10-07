from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step9_checkpoint_audit.py")


def test_step9_checkpoint_audit_parses():
    ast.parse(P.read_text())


def test_step9_checkpoint_audit_is_read_only_and_requires_boundary():
    s = P.read_text()
    upper = s.upper()
    assert '"--since-event-id"' in s
    assert "database writes: 0" in s
    assert "Battlelog requests by audit: 0" in s
    assert " INSERT INTO " not in upper
    assert " UPDATE " not in upper
    assert " DELETE FROM " not in upper


def test_step9_checkpoint_audit_locks_core_acceptance_evidence():
    s = P.read_text()
    assert "collection_attempt_started" in s
    assert "collection_success" in s
    assert "collection_failure" in s
    assert "collection_persistence_failure" in s
    assert "battlelog_throttle" in s
    assert "rolling_1h_max_physical_starts" in s
    assert "BACKGROUND_HOURLY_CEILING = 1296" in s
    assert "duplicate_attempt_keys" in s
    assert "attempts_without_terminal" in s
    assert "terminals_without_start" in s
    assert "foreign_physical_starts" in s


def test_step9_checkpoint_audit_reports_queue_shape_without_mutating_it():
    s = P.read_text()
    assert "FROM collection_jobs" in s
    assert "GROUP BY lane,priority_class,reason,status" in s
    assert "claimed_or_running_jobs_now" in s
