"""Collector duplicate integration regression contracts (offline, no HTTP/DB)."""
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["detailed", "weapon", "vehicle"])
def test_collector_logs_only_confirmed_lease_loser(name):
    source = (Path(__file__).resolve().parents[1] / "bf4ps" / f"{name}_collector.py").read_text()
    assert "except Exception as exc:" in source
    assert "isinstance(exc, RuntimeError)" in source
    assert f"{name} success rejected: job lease is no longer owned" in source
    assert "record_discarded_duplicate(" in source
    assert "return None" in source
    assert "        raise\n" in source


@pytest.mark.parametrize("name", ["detailed", "weapon", "vehicle"])
def test_duplicate_handler_is_after_success_persistence(name):
    source = (Path(__file__).resolve().parents[1] / "bf4ps" / f"{name}_collector.py").read_text()
    assert source.index(f"persist_{name}_success(") < source.index("if isinstance(exc, RuntimeError)")
    assert source.index("if isinstance(exc, RuntimeError)") < source.index("record_discarded_duplicate(")


@pytest.mark.parametrize("name", ["detailed", "weapon", "vehicle"])
def test_finalization_lease_loss_is_classified(name):
    source = (Path(__file__).resolve().parents[1] / "bf4ps" / f"{name}_collector.py").read_text()
    assert f"{name} success rejected during finalization: lease ownership lost" in source


@pytest.mark.parametrize("name,logger", [
    ("detailed", "_record_detailed_persistence_failure"),
    ("weapon", "_record_persistence_failure"),
    ("vehicle", "_record_vehicle_persistence_failure"),
])
def test_unconfirmed_stale_lease_reaches_persistence_failure_audit(name, logger):
    source = (Path(__file__).resolve().parents[1] / "bf4ps" / f"{name}_collector.py").read_text()
    block = source.split("if isinstance(exc, RuntimeError)", 1)[1].split("    return Collected", 1)[0]
    assert "record_discarded_duplicate(" in block
    assert f"{logger}(" in block
    assert block.index("record_discarded_duplicate(") < block.index(f"{logger}(")
    assert "        raise" in block
