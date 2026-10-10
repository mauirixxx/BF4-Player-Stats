"""Offline contract for inert Stage 9C dispatch-ledger migration (no DB or HTTP)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/0005_stage9c_dispatch_ledger.py"
SCHEMA = ROOT / "docs/database-schema-reference.md"


def test_revision_chain_and_documentation():
    tree = ast.parse(MIGRATION.read_text())
    values = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant)
    }
    assert values["revision"] == "0005_stage9c_dispatch_ledger"
    assert values["down_revision"] == "0004_stage9c_supervision_runs"
    schema = SCHEMA.read_text()
    assert "Current documented head: `0005_stage9c_dispatch_ledger`" in schema
    assert "`outbound_dispatches`" in schema


def test_inert_migration_identity_and_safety_contract():
    source = MIGRATION.read_text()
    assert 'op.create_table(' in source
    assert '"outbound_dispatches"' in source
    assert '"uq_outbound_dispatch_identity"' in source
    assert '"payload_fingerprint"' in source
    assert '"outbound_dispatch_phase_timestamps"' in source
    assert '"outbound_dispatch_send_after_admit"' in source
    assert 'SELECT EXISTS (SELECT 1 FROM outbound_dispatches)' in source
    assert 'raise RuntimeError("REFUSING:' in source
    assert "sa.ForeignKey(" not in source
    for forbidden in ("op.execute(", "requests.", "httpx.", "urllib.request"):
        assert forbidden not in source
