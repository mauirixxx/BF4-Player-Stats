"""Durable coordinator journal safety checks (no database required)."""
import json
import pytest

from scripts.phase5b_three_site_manifest import RunManifest
from scripts.phase5b_three_site_recovery import read_intent, write_intent, write_state


def document():
    return RunManifest.build(run_id="journal_test", distribution={"tcou": 1},
                             job_count=2).report()


def test_durable_intent_round_trip(tmp_path):
    path = tmp_path / "run.intent"
    write_intent(path, document())
    assert read_intent(path) == document()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="overwrite"):
        write_intent(path, document())


def test_rejects_tampered_intent(tmp_path):
    path = tmp_path / "run.intent"
    doc = document()
    doc["manifest"]["http_enabled"] = True
    with pytest.raises(ValueError):
        write_intent(path, doc)
    assert not path.exists()


def test_durable_state_and_no_overwrite(tmp_path):
    path = tmp_path / "state.json"
    state = {"run_id": "journal_test", "soldier_ids": [1, 2]}
    write_state(path, state)
    assert json.loads(path.read_text()) == state
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="overwrite"):
        write_state(path, state)
