import ast
from pathlib import Path

SCRIPT = Path("scripts/phase5b_source_churn.py").read_text()


def test_churn_probe_is_read_only_and_network_free():
    tree = ast.parse(SCRIPT)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint({"requests", "httpx", "urllib"})
    lowered = SCRIPT.lower()
    for token in ("insert into", "delete from", "truncate ", "alter table", "create table", "drop table"):
        assert token not in lowered
    assert "database writes: 0" in SCRIPT
    assert "Battlelog requests: 0" in SCRIPT


def test_churn_probe_uses_documented_source_timestamps():
    assert "ss.first_seen_at" in SCRIPT
    assert "ss.last_seen_at" in SCRIPT
    assert "FROM soldier_sources" in SCRIPT
    assert 'SOURCE_TYPE = "bf4sw"' in SCRIPT


def test_churn_probe_does_not_claim_historical_touch_event_counts():
    assert "historical touch-event volume: NOT DERIVABLE from current schema" in SCRIPT
    assert "not every observation" in SCRIPT
    assert "not touch-event counts" in SCRIPT


def test_churn_probe_reports_new_returning_and_observation_span():
    assert "new_24h" in SCRIPT
    assert "returning_24h" in SCRIPT
    assert "new_7d" in SCRIPT
    assert "returning_7d" in SCRIPT
    assert "exact_single_timestamp" in SCRIPT
    assert "span_gte_30d" in SCRIPT


def test_churn_probe_fences_test_database_and_schema_revision():
    assert 'EXPECTED_DATABASE = "bf4_playerstats_test"' in SCRIPT
    assert 'EXPECTED_REVISION = "0003_request_gates"' in SCRIPT
