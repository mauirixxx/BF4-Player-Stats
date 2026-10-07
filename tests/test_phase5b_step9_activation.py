from __future__ import annotations

import ast
from pathlib import Path

PREFLIGHT = Path("scripts/phase5b_step9_activation_preflight.py")
CLEANUP = Path("scripts/phase5b_step9_residue_cleanup.py")


def test_step9_preflight_and_cleanup_parse():
    ast.parse(PREFLIGHT.read_text())
    ast.parse(CLEANUP.read_text())


def test_step9_preflight_is_read_only_and_network_free():
    s = PREFLIGHT.read_text()
    upper = s.upper()
    assert "database writes: 0" in s
    assert "Battlelog requests: 0" in s
    assert " INSERT INTO " not in upper
    assert " UPDATE " not in upper
    assert " DELETE FROM " not in upper
    assert "requests." not in s
    assert "fetch_" not in s


def test_step9_preflight_requires_exact_accepted_residue_and_idle_collectors():
    s = PREFLIGHT.read_text()
    assert "EXPECTED_RESIDUE = 24" in s
    assert "phase5b_step7_endurance" in s
    assert "weapons_state='never_attempted'" in s
    assert "weapons_consecutive_failures=0" in s
    assert "unexpected_background" in s
    assert "current_job_id" in s
    assert "claimed_running" in s


def test_step9_cleanup_requires_explicit_execute_and_exact_shape():
    s = CLEANUP.read_text()
    assert '"--execute"' in s
    assert "EXPECTED_COUNT = 24" in s
    assert "phase5b_step7_endurance" in s
    assert "j.resource = 'weapons'" in s
    assert "j.status = 'pending'" in s
    assert "j.attempt_count = 0" in s
    assert "j.collector_uuid IS NULL" in s
    assert "j.lease_token IS NULL" in s
    assert "cs.weapons_state = 'never_attempted'" in s
    assert "cs.weapons_consecutive_failures = 0" in s


def test_step9_cleanup_only_deletes_queue_rows_and_preserves_evidence():
    s = CLEANUP.read_text()
    assert "DELETE FROM collection_jobs" in s
    assert "DELETE FROM collection_events" not in s
    assert "DELETE FROM collection_state" not in s
    assert "UPDATE collection_state" not in s
    assert "collection_events_deleted=0" in s
    assert "collection_state_rows_rewritten=0" in s


def test_step9_cleanup_uses_transaction_lock_and_postdelete_verification():
    s = CLEANUP.read_text()
    assert "pg_advisory_xact_lock" in s
    assert "FOR UPDATE OF j, cs" in s
    assert "if remaining != 0" in s
