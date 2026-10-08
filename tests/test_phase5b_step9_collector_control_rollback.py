from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step9_collector_control_rollback.py")


def test_rollback_exercise_parses():
    ast.parse(P.read_text())


def test_rollback_exercise_checks_target_and_identity():
    s = P.read_text()
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in s
    assert 'EXPECTED_REVISION = "0003_request_gates"' in s
    assert "pg_is_in_recovery()" in s
    assert "transaction_read_only" in s
    assert "HOSTS.get(host)" in s
    assert "FOR UPDATE" in s
    assert "collector identity mismatch or retired" in s


def test_rollback_exercise_forces_rollback_and_reconnect_verification():
    s = P.read_text()
    assert "tx.rollback()" in s
    assert "with engine.connect() as verify:" in s
    assert "ROLLBACK FAILURE" in s
    assert "persistent database changes: 0" in s
    assert "Battlelog requests: 0" in s


def test_rollback_exercise_does_not_touch_queue_events_or_state():
    s = P.read_text()
    assert "UPDATE collection_jobs" not in s
    assert "DELETE FROM collection_jobs" not in s
    assert "UPDATE collection_events" not in s
    assert "DELETE FROM collection_events" not in s
    assert "UPDATE collection_state" not in s
    assert "DELETE FROM collection_state" not in s
