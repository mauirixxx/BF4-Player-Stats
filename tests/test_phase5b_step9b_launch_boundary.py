from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step9b_launch_boundary.py")


def test_launch_boundary_parses():
    ast.parse(P.read_text())


def test_launch_boundary_is_read_only_and_network_free():
    s = P.read_text()
    assert "INSERT " not in s
    assert "UPDATE " not in s
    assert "DELETE " not in s
    assert "Battlelog requests: 0" in s


def test_launch_boundary_uses_database_clock_and_event_boundary():
    s = P.read_text()
    assert "clock_timestamp() AS cutover_at" in s
    assert "COALESCE(MAX(event_id), 0) AS boundary_event_id" in s
    assert "CUTOVER_AT=" in s
    assert "BOUNDARY_EVENT_ID=" in s


def test_launch_boundary_requires_clean_queue_and_tcou_identity():
    s = P.read_text()
    assert 'CANARY_HOST = "tcou"' in s
    assert "background == 0" in s
    assert "step7 == 0" in s
    assert "owned == 0" in s
    assert 'collector["enabled"] is True' in s
    assert 'collector["drained"] is False' in s
    assert 'collector["current_job_id"] is None' in s
    assert 'collector["retired_at"] is None' in s
