"""Pure offline tests for gateway attempt policy."""
from dataclasses import replace

import pytest

from bf4ps.dispatch_gateway_attempt_policy import (
    GatewayRequest,
    OfflineAttemptRegistry,
    validate_request,
)


def request() -> GatewayRequest:
    return GatewayRequest(attempt_id="attempt-1", resource="detailed", platform="pc", persona_id=236753552)


def test_valid_request():
    validate_request(request())


@pytest.mark.parametrize("change", [
    {"attempt_id": ""},
    {"resource": "unknown"},
    {"platform": "ps3"},
    {"persona_id": 0},
    {"persona_id": True},
    {"method": "POST"},
    {"follow_redirects": True},
    {"automatic_retries": 1},
    {"automatic_retries": True},
])
def test_forbidden_request_parameters(change):
    with pytest.raises(ValueError):
        validate_request(replace(request(), **change))


def test_handoff_requires_reservation():
    registry = OfflineAttemptRegistry()
    assert not registry.handoff(request())


def test_duplicate_attempt_reservation_denied():
    registry = OfflineAttemptRegistry()
    assert registry.reserve(request())
    assert not registry.reserve(request())


def test_handoff_cannot_replay():
    registry = OfflineAttemptRegistry()
    assert registry.reserve(request())
    assert registry.handoff(request())
    assert not registry.handoff(request())


def test_retry_requires_new_attempt_identity():
    registry = OfflineAttemptRegistry()
    assert registry.reserve(request())
    assert registry.handoff(request())
    assert not registry.reserve(request())
    retry = replace(request(), attempt_id="attempt-2")
    assert registry.reserve(retry)
    assert registry.handoff(retry)


@pytest.mark.parametrize("resource", ["detailed", "weapons", "vehicles"])
def test_all_supported_resources(resource):
    validate_request(replace(request(), resource=resource))
