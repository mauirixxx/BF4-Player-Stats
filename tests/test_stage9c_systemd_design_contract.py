"""Offline-only Stage 9C systemd design checks. Never calls systemctl."""
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1] / "docs/phase5b-stage9c-systemd-supervision-design.md"


def test_design_explicitly_prohibits_activation():
    text = DESIGN.read_text()
    assert "No installation, activation, database migration" in text
    assert "dummy units only" in text.lower()


def test_dependent_services_bind_to_guard_and_have_no_restart():
    text = DESIGN.read_text()
    assert "BindsTo=bf4ps-stage9c-guard.service" in text
    assert "After=bf4ps-stage9c-guard.service" in text
    assert "Restart=no" in text
    assert "KillMode=control-group" in text
    assert "RuntimeMaxSec=21600" in text


def test_failure_scenarios_include_sigkill_and_deadline():
    text = DESIGN.read_text()
    assert "SIGKILL" in text
    assert "runtime deadline expiration" in text
    assert "hnl-01" in text and "kah-01" in text and "tcou" in text
