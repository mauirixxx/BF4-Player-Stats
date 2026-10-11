"""Offline host-launcher validation; never starts actual worker subprocesses."""
import json
from unittest.mock import Mock, patch

import pytest

from scripts.phase5b_three_site_manifest import RunManifest
from scripts.phase5b_three_site_soak_host import main


def setup(tmp_path):
    m = RunManifest.build(run_id="soak-host-unit",
                          distribution={"tcou": 3, "kah-01": 3, "hnl-01": 2},
                          job_count=8, claim_limit_per_worker=1, lease_seconds=30)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(m.report()))
    state = tmp_path / "state.json"
    state.write_text("{}")
    return ["--manifest", str(manifest), "--state", str(state),
            "--output-dir", str(tmp_path / "out"), "--duration-seconds", "1", "--execute"]


def fake_process(index, *, returncode=0, claims=1, releases=1):
    p = Mock()
    p.returncode = returncode
    p.poll.return_value = returncode
    p.communicate.return_value = (json.dumps({
        "status": "complete", "claims": claims, "releases": releases,
        "lease_losses": 0, "http_requests": 0, "errors": 0,
    }), "failed")
    return p


def test_three_local_workers(tmp_path, capsys):
    args = setup(tmp_path)
    with patch("scripts.phase5b_three_site_soak_host.socket.gethostname", return_value="tcou"), \
         patch("scripts.phase5b_three_site_soak_host.subprocess.Popen",
               side_effect=[fake_process(i) for i in range(3)]) as popen:
        main(args)
    assert popen.call_count == 3
    assert json.loads(capsys.readouterr().out)["claims"] == 3


def test_child_failure_fails_closed(tmp_path):
    args = setup(tmp_path)
    with patch("scripts.phase5b_three_site_soak_host.socket.gethostname", return_value="tcou"), \
         patch("scripts.phase5b_three_site_soak_host.subprocess.Popen",
               side_effect=[fake_process(0, returncode=1), fake_process(1), fake_process(2)]):
        with pytest.raises(RuntimeError, match="worker 0 failed"):
            main(args)


def test_mismatched_claim_release_rejected(tmp_path):
    args = setup(tmp_path)
    with patch("scripts.phase5b_three_site_soak_host.socket.gethostname", return_value="tcou"), \
         patch("scripts.phase5b_three_site_soak_host.subprocess.Popen",
               side_effect=[fake_process(0, claims=2, releases=1), fake_process(1), fake_process(2)]):
        with pytest.raises(RuntimeError, match="unhealthy"):
            main(args)


def test_execute_required(tmp_path):
    args = setup(tmp_path)
    args.remove("--execute")
    with pytest.raises(SystemExit):
        main(args)


def test_later_worker_failure_detected_while_first_still_running(tmp_path):
    args = setup(tmp_path)
    first = Mock()
    first.poll.return_value = None
    first.communicate.return_value = ("", "")
    first.wait.return_value = 0
    failed = fake_process(1, returncode=7)
    third = fake_process(2)
    with patch("scripts.phase5b_three_site_soak_host.socket.gethostname", return_value="tcou"), \
         patch("scripts.phase5b_three_site_soak_host.subprocess.Popen",
               side_effect=[first, failed, third]):
        with pytest.raises(RuntimeError, match="worker 1 failed"):
            main(args)
    first.terminate.assert_called_once()


def test_host_deadline_rejects_hung_worker(tmp_path):
    args = setup(tmp_path)
    stuck = Mock()
    stuck.poll.return_value = None
    stuck.wait.return_value = 0
    stuck.communicate.return_value = ("", "")
    with patch("scripts.phase5b_three_site_soak_host.socket.gethostname", return_value="tcou"), \
         patch("scripts.phase5b_three_site_soak_host.subprocess.Popen",
               side_effect=[stuck, fake_process(1), fake_process(2)]), \
         patch("scripts.phase5b_three_site_soak_host.time.monotonic",
               side_effect=[0, 100]):
        with pytest.raises(RuntimeError, match="deadline exceeded"):
            main(args)
    stuck.terminate.assert_called_once()
