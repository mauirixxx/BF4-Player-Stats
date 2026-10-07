from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step9_postcleanup_verify.py")


def test_step9_postcleanup_verifier_parses():
    ast.parse(P.read_text())


def test_step9_postcleanup_verifier_is_read_only_and_network_free():
    s = P.read_text()
    upper = s.upper()
    assert "database writes: 0" in s
    assert "Battlelog requests: 0" in s
    assert " INSERT INTO " not in upper
    assert " UPDATE " not in upper
    assert " DELETE FROM " not in upper
    assert "fetch_" not in s


def test_step9_postcleanup_verifier_preserves_accepted_step7_evidence():
    s = P.read_text()
    assert "EXPECTED_ATTEMPTS = 3888" in s
    assert "EXPECTED_UNIQUE_JOBS = 3864" in s
    assert "EXPECTED_RETRIES = 24" in s
    assert "EXPECTED_SUCCESSES = 3864" in s
    assert "EXPECTED_FAILURES = 24" in s
    assert "collection_attempt_started" in s
    assert "collection_success" in s
    assert "collection_failure" in s


def test_step9_postcleanup_verifier_requires_zero_queue_residue():
    s = P.read_text()
    assert "phase5b_step7_endurance" in s
    assert "remaining_step7 == 0" in s
    assert "unexpected_background == 0" in s
    assert "owned == 0" in s


def test_step9_postcleanup_verifier_requires_displaced_states_untouched():
    s = P.read_text()
    assert "EXPECTED_DISPLACED_WEAPON_STATES = 24" in s
    assert "weapons_state='never_attempted'" in s
    assert "weapons_last_attempt_at IS NULL" in s
    assert "weapons_last_success_at IS NULL" in s
    assert "weapons_next_due_at IS NULL" in s
    assert "weapons_consecutive_failures=0" in s
    assert "weapons_last_error_class IS NULL" in s
    assert "weapons_last_error_message IS NULL" in s
