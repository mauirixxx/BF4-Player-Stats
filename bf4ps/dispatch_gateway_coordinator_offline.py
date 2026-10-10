"""Offline composition of gateway request policy and three-host budget authority.

No sockets, HTTP, database, or host-side effects. This is NOT a transport fence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bf4ps.dispatch_gateway_attempt_policy import GatewayRequest, validate_request
from bf4ps.dispatch_three_host_failover_model import ThreeHostGatewayModel


@dataclass
class OfflineGatewayCoordinator:
    """Bind validated immutable request details to one possible-send reservation."""

    capacity: int = 1296
    fleet: ThreeHostGatewayModel = field(init=False)
    requests: dict[str, GatewayRequest] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.fleet = ThreeHostGatewayModel(capacity=self.capacity)

    def reserve(self, host: str, request: GatewayRequest, *, at: int) -> bool:
        validate_request(request)
        if request.attempt_id in self.requests:
            return False
        if not self.fleet.reserve(host, request.attempt_id, at=at):
            return False
        self.requests[request.attempt_id] = request
        return True

    def handoff(self, host: str, request: GatewayRequest) -> bool:
        validate_request(request)
        if self.requests.get(request.attempt_id) != request:
            return False
        return self.fleet.handoff(host, request.attempt_id)

    def transmit(self, host: str, request: GatewayRequest, *, at: int) -> bool:
        """Idealized logical send only; no physical transport exists."""
        validate_request(request)
        if self.requests.get(request.attempt_id) != request:
            return False
        return self.fleet.transmit(host, request.attempt_id, at=at)

    def failover(self, successor: str) -> int:
        return self.fleet.failover(successor)

    def disconnect(self, host: str) -> None:
        self.fleet.disconnect(host)

    def reconnect(self, host: str) -> None:
        self.fleet.reconnect(host)

    def burden(self, *, at: int) -> int:
        return self.fleet.burden(at=at)
