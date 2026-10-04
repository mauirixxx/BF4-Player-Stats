"""Regression coverage for Phase 3E endurance-harness observation semantics."""

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phase3e_endurance_worker.py"
SPEC = importlib.util.spec_from_file_location("phase3e_endurance_worker", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_actionable_depth_above_target_is_telemetry_not_fatal():
    maximum, notice = MODULE.update_actionable_observation(MODULE.TARGET_DEPTH + 1, 6)

    assert maximum == MODULE.TARGET_DEPTH + 1
    assert notice is True


def test_actionable_observation_only_notices_on_new_above_target_high_water_mark():
    maximum, notice = MODULE.update_actionable_observation(8, 7)
    assert (maximum, notice) == (8, True)

    maximum, notice = MODULE.update_actionable_observation(7, maximum)
    assert (maximum, notice) == (8, False)

    maximum, notice = MODULE.update_actionable_observation(8, maximum)
    assert (maximum, notice) == (8, False)


def test_actionable_observation_below_target_remains_normal_telemetry():
    maximum, notice = MODULE.update_actionable_observation(MODULE.TARGET_DEPTH, 4)

    assert maximum == MODULE.TARGET_DEPTH
    assert notice is False
