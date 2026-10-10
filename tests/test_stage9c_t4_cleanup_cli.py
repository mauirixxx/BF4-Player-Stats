"""Offline CLI safety tests: rejected commands must not open PostgreSQL."""
import sys
import pytest
from scripts import phase5b_stage9c_t4_coordinator as coordinator

RUN_ID = "00000000-0000-0000-0000-000000000001"

@pytest.mark.parametrize("action", ["cleanup", "recover"])
@pytest.mark.parametrize("confirmations", [
    [],
    ["--confirm-all-participants-stopped"],
    ["--confirm-preserved-evidence"],
])
def test_destructive_actions_require_both_attestations(monkeypatch, capsys, action, confirmations):
    monkeypatch.setattr(sys, "argv", ["t4_coordinator", action, "--execute",
                                      "--run-id", RUN_ID, *confirmations])
    # If CLI validation regresses, fail before any DB operation.
    monkeypatch.setattr(coordinator, "refuse_unsafe_target",
                        lambda url: pytest.fail("reached database target validation"))
    with pytest.raises(SystemExit) as exc:
        coordinator.main()
    assert exc.value.code == 2
    assert "confirmations" in capsys.readouterr().err

@pytest.mark.parametrize("action", ["seed", "release", "inspect"])
def test_rollback_probe_not_accepted_for_other_actions(monkeypatch, action):
    monkeypatch.setattr(sys, "argv", ["t4_coordinator", action, "--execute",
                                      "--run-id", RUN_ID, "--rollback-probe"])
    monkeypatch.setattr(coordinator, "refuse_unsafe_target",
                        lambda url: pytest.fail("reached database target validation"))
    with pytest.raises(SystemExit) as exc:
        coordinator.main()
    assert exc.value.code == 2
