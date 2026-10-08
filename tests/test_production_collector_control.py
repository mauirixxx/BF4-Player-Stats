from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/bf4ps_production_collector_control.py")


def test_production_collector_control_parses():
    ast.parse(P.read_text())


def test_control_is_fail_closed():
    s = P.read_text()
    assert 'choices=("drain", "resume")' in s
    assert "--execute" in s
    assert "REFUSING: --execute is required" in s
    assert "EXPECTED_DATABASE = \"bf4_playerstats_test\"" in s
    assert "EXPECTED_REVISION = \"0003_request_gates\"" in s
    assert "pg_is_in_recovery()" in s
    assert "transaction_read_only" in s


def test_control_validates_frozen_identity_before_mutation():
    s = P.read_text()
    assert "HOSTS.get(host)" in s
    assert "FOR UPDATE" in s
    assert 'row["collector_uuid"]' in s
    assert 'row["collector_name"]' in s
    assert 'row["hostname"]' in s
    assert 'row["lane"]' in s
    assert 'row["egress_key"]' in s
    assert 'row["retired_at"]' in s
    assert "collector identity drift" in s


def test_control_mutates_only_drain_state():
    tree = ast.parse(P.read_text())
    sql_strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    updates = [s for s in sql_strings if "UPDATE collectors" in s]
    assert len(updates) == 1
    normalized = " ".join(updates[0].split())
    assert "SET drained=:drained, updated_at=now()" in normalized
    assert "current_job_id=" not in normalized
    assert "enabled=" not in normalized


def test_control_does_not_touch_queue_or_events():
    s = P.read_text()
    assert "UPDATE collection_jobs" not in s
    assert "DELETE FROM collection_jobs" not in s
    assert "UPDATE collection_events" not in s
    assert "DELETE FROM collection_events" not in s
    assert "UPDATE collection_state" not in s
    assert "DELETE FROM collection_state" not in s
