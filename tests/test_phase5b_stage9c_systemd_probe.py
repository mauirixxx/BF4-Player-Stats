"""Offline tests of the harmless Stage 9C systemd dependency probe."""
from scripts.phase5b_stage9c_systemd_probe import commands


def test_probe_uses_only_sleep_and_systemd_run():
    guard, worker, first, second = commands("bf4ps-stage9c-probe-test")
    assert first[0] == second[0] == "systemd-run"
    assert first[-2:] == second[-2:] == ["/usr/bin/sleep", "100"]
    assert "BindsTo=" + guard in second
    assert "After=" + guard in second
    assert worker.endswith("-worker.service")


def test_probe_is_bounded_and_collected():
    _, _, first, second = commands("bf4ps-stage9c-probe-test")
    assert "--collect" in first and "--collect" in second
    assert "--property=RuntimeMaxSec=120" in first
    assert "--property=RuntimeMaxSec=120" in second
