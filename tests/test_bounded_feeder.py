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


def test_feeder_rejects_empty_explicit_cohort():
    with pytest.raises(ValueError, match="allowed_soldier_ids must not be empty"):
        replenish_detailed_bootstrap(
            None, target_depth=1, max_soldier_id=10, allowed_soldier_ids=()
        )  # type: ignore[arg-type]


def test_feeder_rejects_nonpositive_explicit_cohort_id():
    with pytest.raises(ValueError, match="only positive IDs"):
        replenish_detailed_bootstrap(
            None, target_depth=1, max_soldier_id=10, allowed_soldier_ids=(0, 3)
        )  # type: ignore[arg-type]


def test_feeder_rejects_explicit_cohort_beyond_boundary():
    with pytest.raises(ValueError, match="cannot exceed max_soldier_id"):
        replenish_detailed_bootstrap(
            None, target_depth=1, max_soldier_id=10, allowed_soldier_ids=(3, 11)
        )  # type: ignore[arg-type]


def test_feeder_rejects_nonpositive_attempt_ceiling():
    with pytest.raises(ValueError, match="max_total_attempts must be positive"):
        replenish_detailed_bootstrap(
            None,
            target_depth=1,
            max_soldier_id=10,
            allowed_soldier_ids=(3,),
            max_total_attempts=0,
        )  # type: ignore[arg-type]


def test_feeder_attempt_ceiling_requires_explicit_cohort():
    with pytest.raises(ValueError, match="max_total_attempts requires allowed_soldier_ids"):
        replenish_detailed_bootstrap(
            None,
            target_depth=1,
            max_soldier_id=10,
            max_total_attempts=10,
        )  # type: ignore[arg-type]


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _ScalarsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _ConcurrentDepthConnection:
    """Minimal feeder connection that simulates collector-side depth movement."""

    def __init__(self):
        self.depth_reads = iter((5, 7))

    def execute(self, statement, params=None):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            return _ScalarResult(None)
        if "SELECT COUNT(*)" in sql and "FROM collection_jobs" in sql:
            return _ScalarResult(next(self.depth_reads))
        if "SELECT s.soldier_id" in sql:
            return _ScalarsResult([])
        raise AssertionError(f"unexpected SQL in regression fixture: {sql}")


def test_feeder_post_depth_above_target_is_telemetry_not_failure():
    conn = _ConcurrentDepthConnection()

    result = replenish_detailed_bootstrap(
        conn,  # type: ignore[arg-type]
        target_depth=6,
        max_soldier_id=10,
    )

    assert result.actionable_before == 5
    assert result.deficit == 1
    assert result.created == 0
    assert result.actionable_after == 7
