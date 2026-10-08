"""Pure offline tests for the Stage 9C dummy systemd generator."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/phase5b_stage9c_systemd_dummy.py"


def test_dry_run_writes_nothing(tmp_path):
    output = tmp_path / "units"
    result = subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(output)],
                            capture_output=True, text=True, check=True)
    assert "DRY RUN" in result.stdout
    assert not output.exists()


def test_staged_units_have_safe_dependency_contract(tmp_path):
    output = tmp_path / "units"
    subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(output), "--write"],
                   capture_output=True, text=True, check=True)
    units = {p.name: p.read_text() for p in output.glob("*.service")}
    assert len(units) == 3
    guard = "bf4ps-stage9c-test-guard.service"
    assert guard in units
    for name, content in units.items():
        assert "ExecStart=/usr/bin/sleep 3600" in content
        assert "Restart=no" in content
        assert "RuntimeMaxSec=90" in content
        assert "KillMode=control-group" in content
        assert "BF4PS_DATABASE_URL" not in content
        if name != guard:
            assert f"BindsTo={guard}" in content
            assert f"After={guard}" in content


def test_refuses_systemd_installation_directory():
    result = subprocess.run([sys.executable, str(SCRIPT), "--output-dir",
                             "/etc/systemd/system", "--write"],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "REFUSING" in result.stderr
