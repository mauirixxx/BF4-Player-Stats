import ast
from pathlib import Path


SCRIPT = Path("scripts/phase5b_scheduler_db_validate.py").read_text()


def test_db_validation_is_fenced_to_test_database_and_current_revision():
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in SCRIPT
    assert 'EXPECTED_REVISION = "0003_request_gates"' in SCRIPT
    assert "SELECT current_database()" in SCRIPT
    assert "SELECT version_num FROM alembic_version" in SCRIPT


def test_db_validation_requires_one_explicit_soldier():
    assert 'parser.add_argument("--soldier-id", type=int, required=True)' in SCRIPT
    assert "WHERE s.soldier_id = :soldier_id" in SCRIPT
    assert "choose an idle soldier" in SCRIPT


def test_db_validation_is_rollback_only_and_has_no_battlelog_runtime():
    assert "tx = conn.begin()" in SCRIPT
    assert "tx.rollback()" in SCRIPT
    assert "tx.commit()" not in SCRIPT
    tree = ast.parse(SCRIPT)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert "battlelog_" not in SCRIPT.lower()
    assert imported_roots.isdisjoint({"requests", "httpx", "urllib"})


def test_db_validation_exercises_frozen_materialization_scenarios():
    assert "bf4sw_new_soldier" in SCRIPT
    assert "bf4sw_active_refresh" in SCRIPT
    assert 'assert result.source_class == "recent"' in SCRIPT
    assert "replay.created_resources == ()" in SCRIPT
    assert '{"detailed", "weapons", "vehicles"}' in SCRIPT
