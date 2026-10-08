from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step9_materialization_process_check.py")


def test_materialization_process_check_parses():
    ast.parse(P.read_text())


def test_process_check_is_local_and_read_only():
    s = P.read_text()
    assert 'Path("/proc")' in s
    assert "database writes: 0" in s
    assert "Battlelog requests: 0" in s
    assert "create_engine" not in s
    assert "requests." not in s
    assert "httpx." not in s


def test_process_check_detects_materialization_flag():
    s = P.read_text()
    assert 'MATERIALIZE_FLAG = "--materialize-production-jobs"' in s
    assert "materializing = [row for row in discoveries if row[2]]" in s
    assert "passed = not materializing" in s


def test_process_check_targets_discovery_processes():
    s = P.read_text()
    assert "bf4ps.discovery_service" in s
    assert "bf4ps/discovery_service.py" in s
    assert "scripts/bf4ps_discovery" in s
