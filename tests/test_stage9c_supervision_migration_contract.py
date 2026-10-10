"""Offline structural checks; does not connect to PostgreSQL or activate Stage 9C."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/0004_stage9c_supervision_runs.py"
SCHEMA = ROOT / "docs/database-schema-reference.md"


def test_migration_revision_chain():
    tree = ast.parse(MIGRATION.read_text())
    assigns = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant)
    }
    assert assigns["revision"] == "0004_stage9c_supervision_runs"
    assert assigns["down_revision"] == "0003_request_gates"


def test_supervision_migration_is_inert_and_reversible():
    source = MIGRATION.read_text()
    assert 'op.create_table(' in source
    assert 'stage9c_supervision_runs' in source
    assert 'uq_stage9c_one_active_run' in source
    assert "interval '6 hours'" in source
    assert "state = 'active'" in source
    assert 'op.drop_table("stage9c_supervision_runs")' in source
    assert 'op.execute(' not in source
    for forbidden in ("collection_jobs", "collection_events", "UPDATE collectors"):
        assert forbidden not in source


def test_schema_reference_keeps_supervision_and_tracks_current_head():
    schema = SCHEMA.read_text()
    assert "Current documented head: `0005_stage9c_dispatch_ledger`" in schema
    assert "| `0004_stage9c_supervision_runs` |" in schema
    assert "### `stage9c_supervision_runs`" in schema
    assert "sticky abort" in schema
