"""Offline policy -> possible-send accounting -> failover integration."""
from dataclasses import replace

import pytest

from bf4ps.dispatch_gateway_attempt_policy import GatewayRequest
from bf4ps.dispatch_gateway_coordinator_offline import OfflineGatewayCoordinator


def req(identity: str = "a") -> GatewayRequest:
    return GatewayRequest(identity, "detailed", "pc", 236753552)


def test_valid_request_reserve_handoff_confirm():
    c = OfflineGatewayCoordinator(capacity=1)
    assert c.reserve("tcou", req(), at=0)
    assert c.burden(at=0) == 1
    assert c.handoff("tcou", req())
    assert c.transmit("tcou", req(), at=1)
    assert c.burden(at=1) == 1
    assert c.burden(at=3602) == 0


def test_invalid_redirect_cannot_reserve():
    c = OfflineGatewayCoordinator(capacity=1)
    with pytest.raises(ValueError, match="redirect"):
        c.reserve("tcou", replace(req(), follow_redirects=True), at=0)
    assert c.burden(at=0) == 0


def test_invalid_retry_cannot_reserve():
    c = OfflineGatewayCoordinator(capacity=1)
    with pytest.raises(ValueError, match="retries"):
        c.reserve("tcou", replace(req(), automatic_retries=1), at=0)
    assert c.burden(at=0) == 0


def test_request_identity_immutable_after_reservation():
    c = OfflineGatewayCoordinator(capacity=2)
    assert c.reserve("tcou", req(), at=0)
    modified = replace(req(), resource="weapons")
    assert not c.handoff("tcou", modified)
    assert not c.transmit("tcou", modified, at=1)
    assert c.handoff("tcou", req())


def test_unreserved_handoff_and_transmit_refused():
    c = OfflineGatewayCoordinator()
    assert not c.handoff("tcou", req())
    assert not c.transmit("tcou", req(), at=0)


def test_duplicate_attempt_identity_refused_even_after_send():
    c = OfflineGatewayCoordinator(capacity=2)
    assert c.reserve("tcou", req(), at=0)
    assert c.handoff("tcou", req())
    assert c.transmit("tcou", req(), at=1)
    assert not c.reserve("tcou", req(), at=3602)


def test_crash_failover_keeps_old_uncertain_capacity():
    c = OfflineGatewayCoordinator(capacity=1)
    assert c.reserve("tcou", req(), at=0)
    assert c.handoff("tcou", req())
    c.disconnect("tcou")
    c.failover("kah-01")
    assert c.burden(at=99999) == 1
    assert not c.reserve("kah-01", req("new"), at=99999)
    c.reconnect("tcou")
    assert not c.transmit("tcou", req(), at=100000)


def test_successor_can_use_remaining_capacity_with_distinct_attempt():
    c = OfflineGatewayCoordinator(capacity=2)
    assert c.reserve("tcou", req(), at=0)
    c.failover("hnl-01")
    assert c.reserve("hnl-01", req("new"), at=3602)
    assert c.handoff("hnl-01", req("new"))
    assert c.transmit("hnl-01", req("new"), at=3603)
    assert c.burden(at=3603) == 2


def test_no_free_retry_after_ambiguous_attempt():
    c = OfflineGatewayCoordinator(capacity=1)
    assert c.reserve("tcou", req(), at=0)
    assert c.handoff("tcou", req())
    assert not c.reserve("tcou", req("retry"), at=99999)


def test_failed_reservation_does_not_claim_identity():
    c = OfflineGatewayCoordinator(capacity=1)
    assert c.reserve("tcou", req(), at=0)
    assert not c.reserve("tcou", req("b"), at=1)
    assert "b" not in c.requests
