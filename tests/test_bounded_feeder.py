import pytest

from bf4ps.bounded_feeder import replenish_detailed_bootstrap


def test_feeder_requires_positive_target():
    with pytest.raises(ValueError, match="target_depth must be positive"):
        replenish_detailed_bootstrap(None, target_depth=0, max_soldier_id=10)  # type: ignore[arg-type]


def test_feeder_refuses_unbounded_population():
    with pytest.raises(ValueError, match="max_soldier_id is required"):
        replenish_detailed_bootstrap(None, target_depth=10, max_soldier_id=None)  # type: ignore[arg-type]


def test_feeder_requires_positive_population_boundary():
    with pytest.raises(ValueError, match="max_soldier_id must be positive"):
        replenish_detailed_bootstrap(None, target_depth=10, max_soldier_id=0)  # type: ignore[arg-type]
