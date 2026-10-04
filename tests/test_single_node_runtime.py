from uuid import uuid4

import pytest

from bf4ps.detailed_collector import CollectorIdentity
from bf4ps.single_node_runtime import SingleNodeRuntimeConfig, _validate_config


def valid_config(**changes):
    values = dict(
        target_depth=3,
        max_soldier_id=6,
        max_jobs=3,
        request_interval_seconds=2.0,
    )
    values.update(changes)
    return SingleNodeRuntimeConfig(**values)


def test_bounded_runtime_requires_positive_job_ceiling():
    with pytest.raises(ValueError, match="max_jobs must be positive"):
        _validate_config(valid_config(max_jobs=0))


def test_bounded_runtime_requires_explicit_positive_soldier_boundary():
    with pytest.raises(ValueError, match="max_soldier_id must be positive"):
        _validate_config(valid_config(max_soldier_id=0))


def test_bounded_runtime_requires_positive_target_depth():
    with pytest.raises(ValueError, match="target_depth must be positive"):
        _validate_config(valid_config(target_depth=0))


def test_bounded_runtime_accepts_conservative_validation_config():
    _validate_config(valid_config())


def test_collector_identity_fixture_is_stable_and_background():
    collector_uuid = uuid4()
    identity = CollectorIdentity(
        collector_uuid=collector_uuid,
        collector_name="phase2-auto-tcou",
        hostname="tcou",
        egress_key="phase2-auto-tcou",
        lane="background",
    )
    assert identity.collector_uuid == collector_uuid
    assert identity.lane == "background"
