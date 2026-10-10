"""Collector duplicate integration regression contracts (offline, no HTTP/DB)."""
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["detailed", "weapon", "vehicle"])
def test_collector_logs_only_confirmed_lease_loser(name):
    source = (Path(__file__).resolve().parents[1] / "bf4ps" / f"{name}_collector.py").read_text()
    assert "except RuntimeError as exc:" in source
    assert f"{name} success rejected: job lease is no longer owned" in source
    assert "record_discarded_duplicate(" in source
    assert "return None" in source
    assert "        raise\n" in source


@pytest.mark.parametrize("name", ["detailed", "weapon", "vehicle"])
def test_duplicate_handler_is_after_success_persistence(name):
    source = (Path(__file__).resolve().parents[1] / "bf4ps" / f"{name}_collector.py").read_text()
    assert source.index(f"persist_{name}_success(") < source.index("except RuntimeError as exc:")
    assert source.index("except RuntimeError as exc:") < source.index("record_discarded_duplicate(")
