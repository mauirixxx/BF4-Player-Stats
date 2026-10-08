from __future__ import annotations

import ast
from pathlib import Path

P = Path("scripts/phase5b_step9_activation_ready.py")


def test_activation_ready_parses():
    ast.parse(P.read_text())


def test_activation_ready_is_read_only():
    s = P.read_text()
    upper = s.upper()
    assert "database writes: 0" in s
    assert "Battlelog requests: 0" in s
    assert " INSERT INTO " not in upper
    assert " UPDATE " not in upper
    assert " DELETE FROM " not in upper


def test_activation_ready_requires_clean_postcleanup_queue():
    s = P.read_text()
    assert "background == 0" in s
    assert "step7 == 0" in s
    assert "owned == 0" in s
    assert "reason='phase5b_step7_endurance'" in s


def test_activation_ready_validates_stable_collectors():
    s = P.read_text()
    assert "HOSTS.values()" in s
    assert "actual == expected" in s
    assert "retired == 0" in s
    assert "current_jobs == 0" in s


def test_activation_ready_does_not_fake_external_process_proof():
    s = P.read_text()
    assert "external_materialization_process_check=REQUIRED" in s
