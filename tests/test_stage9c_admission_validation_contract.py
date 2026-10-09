"""Offline regression guards for the Stage 9C admission concurrency harness.

These tests deliberately require no PostgreSQL connection. The live concurrency
harness remains a separate, explicitly authorized disposable-DB operation.
"""
from pathlib import Path

from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target


def test_shared_background_budget_is_frozen():
    assert BACKGROUND_SLOTS_PER_HOUR == 1296


def test_existing_disposable_database_allowlist_remains_exact():
    url = (
        "postgresql+psycopg://bf4ps_stage9c_integration:secret@"
        "mak-db-02.bf4statusbot.com/bf4ps_scratch_stage9c_integration"
    )
    assert refuse_unsafe_target(url) == "bf4ps_scratch_stage9c_integration"


def test_concurrency_design_requires_independent_transactions():
    design = Path("docs/stage9c-admission-concurrency-validation.md").read_text()
    assert "independent PostgreSQL connections" in design
    assert "No live Battlelog" in design
    assert "HOLD" in design
