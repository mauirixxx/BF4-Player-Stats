"""Offline counterexamples for buffered writes crossing a gateway failover.

This model deliberately permits a previously queued transport write to escape
after leadership fencing. It has NO sockets, database or physical HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bf4ps.dispatch_gateway_attempt_policy import GatewayRequest
from bf4ps.dispatch_gateway_coordinator_offline import OfflineGatewayCoordinator


@dataclass
class BufferedFailoverScenario:
    capacity: int = 1296
    coordinator: OfflineGatewayCoordinator = field(init=False)
    buffered: dict[str, str] = field(default_factory=dict)
    observed_transmissions: list[tuple[str, str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.coordinator = OfflineGatewayCoordinator(capacity=self.capacity)

    def queue(self, host: str, request: GatewayRequest, *, at: int) -> bool:
        if not self.coordinator.reserve(host, request, at=at):
            return False
        if not self.coordinator.handoff(host, request):
            return False
        self.buffered[request.attempt_id] = host
        return True

    def failover(self, successor: str) -> int:
        return self.coordinator.failover(successor)

    def flush_buffer(self, attempt_id: str, *, at: int) -> bool:
        """Model kernel/transport emission independent of SQL leadership.

        Returns True when a queued write may escape after a leadership change.
        This is a counterexample, NOT an authorized coordinator transmission.
        """
        host = self.buffered.pop(attempt_id, None)
        if host is None:
            return False
        self.observed_transmissions.append((attempt_id, host, at))
        return True

    def observed_in_window(self, *, at: int, seconds: int = 3600) -> int:
        return sum(at - seconds < when <= at for _, _, when in self.observed_transmissions)
