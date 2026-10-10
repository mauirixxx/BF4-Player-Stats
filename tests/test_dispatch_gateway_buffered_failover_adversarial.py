"""Offline buffered-write/failover adversarial schedules."""
from bf4ps.dispatch_gateway_attempt_policy import GatewayRequest
from bf4ps.dispatch_gateway_buffered_failover_adversarial import BufferedFailoverScenario


def req(identity: str) -> GatewayRequest:
    return GatewayRequest(identity, "detailed", "pc", 236753552)


def test_old_buffer_can_escape_after_generation_change():
    s = BufferedFailoverScenario(capacity=1)
    assert s.queue("tcou", req("old"), at=0)
    assert s.failover("kah-01") == 2
    assert not s.coordinator.transmit("tcou", req("old"), at=3602)
    assert s.flush_buffer("old", at=3602)
    assert s.observed_in_window(at=3602) == 1
    assert s.coordinator.burden(at=3602) == 1


def test_old_ambiguous_capacity_blocks_successor():
    s = BufferedFailoverScenario(capacity=1)
    assert s.queue("tcou", req("old"), at=0)
    s.failover("hnl-01")
    assert not s.queue("hnl-01", req("new"), at=3602)
    assert s.flush_buffer("old", at=3602)


def test_distinct_attempts_are_charged_across_generations():
    s = BufferedFailoverScenario(capacity=2)
    assert s.queue("tcou", req("old"), at=0)
    s.failover("kah-01")
    assert s.queue("kah-01", req("new"), at=3602)
    assert s.flush_buffer("old", at=3602)
    assert s.flush_buffer("new", at=3602)
    assert s.observed_in_window(at=3602) == 2
    assert s.coordinator.burden(at=3602) == 2


def test_same_buffer_cannot_flush_twice_in_model():
    s = BufferedFailoverScenario(capacity=1)
    assert s.queue("tcou", req("old"), at=0)
    assert s.flush_buffer("old", at=1)
    assert not s.flush_buffer("old", at=2)


def test_unreserved_buffer_cannot_flush():
    s = BufferedFailoverScenario()
    assert not s.flush_buffer("missing", at=1)


def test_duplicate_identity_cannot_queue_on_successor():
    s = BufferedFailoverScenario(capacity=2)
    assert s.queue("tcou", req("old"), at=0)
    s.failover("kah-01")
    assert not s.queue("kah-01", req("old"), at=1)


def test_admission_timestamp_cannot_age_out_ambiguous_write():
    s = BufferedFailoverScenario(capacity=1)
    assert s.queue("tcou", req("old"), at=0)
    s.failover("hnl-01")
    assert s.coordinator.burden(at=86400) == 1
    assert s.flush_buffer("old", at=86400)
    assert s.observed_in_window(at=86400) == 1


def test_disconnected_old_owner_buffer_still_uncertain():
    s = BufferedFailoverScenario(capacity=1)
    assert s.queue("tcou", req("old"), at=0)
    s.coordinator.disconnect("tcou")
    s.failover("kah-01")
    assert s.flush_buffer("old", at=3602)
    assert s.coordinator.burden(at=3602) == 1
