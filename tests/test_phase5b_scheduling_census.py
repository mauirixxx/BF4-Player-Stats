import ast
from pathlib import Path

SCRIPT = Path("scripts/phase5b_scheduling_census.py").read_text()


def test_census_is_read_only_and_network_free():
    tree = ast.parse(SCRIPT)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert "database writes: 0" in SCRIPT
    assert "Battlelog requests: 0" in SCRIPT
    assert imported_roots.isdisjoint({"requests", "httpx", "urllib"})
    lowered = SCRIPT.lower()
    for sql_token in ("insert into", "delete from", "truncate ", "alter table", "create table", "drop table"):
        assert sql_token not in lowered


def test_census_constructs_only_documented_resource_prefixed_state_columns():
    tree = ast.parse(SCRIPT)
    resources = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "RESOURCES":
                    resources = tuple(
                        elt.value for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    )
    assert resources == ("detailed", "profile", "weapons", "vehicles")
    for suffix in ("_state", "_last_success_at", "_consecutive_failures", "_last_error_class"):
        assert f"{{resource}}{suffix}" in SCRIPT
    assert "collection_state WHERE resource" not in SCRIPT


def test_census_reports_queue_collectors_gates_and_durable_attempts():
    assert "FROM collection_jobs" in SCRIPT
    assert "FROM collectors" in SCRIPT
    assert "FROM request_gates" in SCRIPT
    assert "event_type='collection_attempt_started'" in SCRIPT


def test_source_recency_is_not_mislabeled_as_gameplay_activity():
    assert "source recency is discovery/source observation, NOT proven gameplay activity" in SCRIPT
    assert "FROM soldier_sources" in SCRIPT


def test_census_fences_test_database_and_schema_revision():
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in SCRIPT
    assert 'EXPECTED_REVISION = "0003_request_gates"' in SCRIPT
    assert "SELECT current_database()" in SCRIPT
    assert "SELECT version_num FROM alembic_version" in SCRIPT
