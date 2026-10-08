"""Static safety contract: no DB connections, systemd or Battlelog requests."""
import ast
import inspect

from scripts import phase5b_stage9c_watchdog as watchdog
from scripts import phase5b_stage9c_local_guard as guard
from bf4ps.stage9c_supervision import REVISION


def test_both_runtime_paths_require_revision_four():
    assert watchdog.EXPECTED_REV == guard.EXPECTED_REV == REVISION


def test_guard_requires_run_lease_after_registry_validation():
    src = inspect.getsource(guard.check_db)
    assert "require_guard_lease(conn, run_id)" in src
    assert src.index('if not row["enabled"] or row["drained"]') < src.index("require_guard_lease(conn, run_id)")


def test_watchdog_requires_fenced_identity_and_boundary():
    src = inspect.getsource(watchdog.main)
    for arg in ("--run-id", "--watchdog-owner", "--watchdog-generation",
                "BOUNDARY_EVENT_ID", "CUTOVER_AT"):
        assert arg in src


def test_watchdog_abort_and_drain_share_transaction():
    src = inspect.getsource(watchdog.main)
    tree = ast.parse(src)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    names = [node.func.id for node in calls if isinstance(node.func, ast.Name)]
    assert "abort_owned_run" in names
    assert "drain_fleet" in names
    assert "renew_after_inspection" in names
    assert src.index("abort_owned_run(") < src.index("drain_fleet(conn)")
    assert src.count("with engine.begin() as conn:") == 1
    assert "inspection_passed=True" in src
    assert "return 3" in src


def test_guard_stops_only_known_units():
    assert guard.COLLECTOR_UNIT == "bf4ps-stage9c-collector.service"
    assert guard.MATERIALIZER_UNIT == "bf4ps-stage9c-materializer.service"
