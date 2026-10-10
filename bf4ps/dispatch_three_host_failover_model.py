"""Offline three-host gateway failover state machine.

No network, database, clock, process, or firewall side effects.
Safety is conditional on a non-bypassable transport boundary and one physical
send per attempt, neither of which this model can establish.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bf4ps.dispatch_possible_send_model import PossibleSendAuthority


HOSTS = ("tcou", "kah-01", "hnl-01")


@dataclass
class ThreeHostGatewayModel:
    capacity: int = 1296
    generation: int = 1
    leader: str = "tcou"
    connected: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(HOSTS, True))
    reservations: dict[str, tuple[str, int]] = field(default_factory=dict)
    handed_off: set[str] = field(default_factory=set)
    authority: PossibleSendAuthority = field(init=False)

    def __post_init__(self) -> None:
        self.authority = PossibleSendAuthority(self.capacity)
        if self.leader not in HOSTS:
            raise ValueError("unknown leader")

    def reserve(self, host: str, identity: str, *, at: int) -> bool:
        if host not in HOSTS:
            raise ValueError("unknown host")
        if host != self.leader or not self.connected[host]:
            return False
        admitted = self.authority.reserve(identity, at=at)
        if admitted:
            self.reservations[identity] = (host, self.generation)
        return admitted

    def handoff(self, host: str, identity: str) -> bool:
        if host != self.leader or not self.connected.get(host, False):
            return False
        if self.reservations.get(identity) != (host, self.generation):
            return False
        if identity in self.handed_off:
            return False
        self.handed_off.add(identity)
        return True

    def disconnect(self, host: str) -> None:
        if host not in HOSTS:
            raise ValueError("unknown host")
        self.connected[host] = False

    def reconnect(self, host: str) -> None:
        if host not in HOSTS:
            raise ValueError("unknown host")
        self.connected[host] = True

    def failover(self, successor: str) -> int:
        if successor not in HOSTS:
            raise ValueError("unknown host")
        if not self.connected[successor]:
            raise ValueError("successor disconnected")
        if successor == self.leader:
            raise ValueError("successor already leader")
        self.generation += 1
        self.leader = successor
        # Deliberately retain ALL prior uncertain attempts.
        return self.generation

    def transmit(self, host: str, identity: str, *, at: int) -> bool:
        """Idealized atomic fence; does not model buffered socket writes."""
        if host != self.leader or not self.connected.get(host, False):
            return False
        if self.reservations.get(identity) != (host, self.generation):
            return False
        if identity not in self.handed_off:
            return False
        self.handed_off.remove(identity)
        self.authority.confirm_send(identity, sent_at=at)
        return True

    def burden(self, *, at: int) -> int:
        return self.authority.burden(at)
