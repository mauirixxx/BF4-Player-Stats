"""Offline three-host gateway failover tests; no real dispatch."""
import pytest

from bf4ps.dispatch_three_host_failover_model import ThreeHostGatewayModel


def test_disconnected_leader_fails_closed():
    m = ThreeHostGatewayModel(capacity=2)
    m.disconnect("tcou")
    assert not m.reserve("tcou", "a", at=0)
    assert not m.reserve("kah-01", "a", at=0)


def test_failover_retains_old_possible_send_burden():
    m = ThreeHostGatewayModel(capacity=1)
    assert m.reserve("tcou", "old", at=0)
    assert m.handoff("tcou", "old")
    m.disconnect("tcou")
    assert m.failover("kah-01") == 2
    assert m.burden(at=99999) == 1
    assert not m.reserve("kah-01", "new", at=99999)


def test_reconnected_old_leader_cannot_send_or_reserve():
    m = ThreeHostGatewayModel(capacity=2)
    assert m.reserve("tcou", "old", at=0)
    assert m.handoff("tcou", "old")
    m.disconnect("tcou")
    m.failover("hnl-01")
    m.reconnect("tcou")
    assert not m.transmit("tcou", "old", at=3602)
    assert not m.reserve("tcou", "rogue", at=3602)


def test_successor_can_use_only_remaining_capacity():
    m = ThreeHostGatewayModel(capacity=2)
    assert m.reserve("tcou", "old", at=0)
    m.failover("kah-01")
    assert m.reserve("kah-01", "new", at=3602)
    assert not m.reserve("kah-01", "extra", at=3602)


def test_successor_handoff_and_send():
    m = ThreeHostGatewayModel(capacity=2)
    m.failover("hnl-01")
    assert m.reserve("hnl-01", "a", at=1)
    assert m.handoff("hnl-01", "a")
    assert m.transmit("hnl-01", "a", at=2)
    assert not m.transmit("hnl-01", "a", at=3)


def test_disconnected_successor_refused():
    m = ThreeHostGatewayModel()
    m.disconnect("kah-01")
    with pytest.raises(ValueError, match="disconnected"):
        m.failover("kah-01")


def test_invalid_host_refused():
    m = ThreeHostGatewayModel()
    with pytest.raises(ValueError, match="unknown"):
        m.reserve("unknown", "x", at=0)
    with pytest.raises(ValueError, match="unknown"):
        m.disconnect("unknown")


def test_duplicate_attempt_identity_across_hosts_refused():
    m = ThreeHostGatewayModel(capacity=2)
    assert m.reserve("tcou", "x", at=0)
    m.failover("kah-01")
    with pytest.raises(ValueError, match="fresh"):
        m.reserve("kah-01", "x", at=1)


def test_failed_handoff_without_reservation():
    m = ThreeHostGatewayModel()
    assert not m.handoff("tcou", "missing")
