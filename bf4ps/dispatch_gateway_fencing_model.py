"""Offline gateway fencing and replay model; never sends HTTP.

This model is a logical safety oracle under explicitly assumed enforcement:
a gateway generation is fenced atomically at the send boundary, every send
attempt has at most one physical transmission, and no direct egress bypasses
the gateway. It does NOT implement or prove those external assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bf4ps.dispatch_possible_send_model import PossibleSendAuthority


@dataclass
class FencedGatewayModel:
    capacity: int
    generation: int = 1
    authority: PossibleSendAuthority = field(init=False)
    owners: dict[str, int] = field(default_factory=dict)
    handed_off: set[str] = field(default_factory=set)
    transmitted: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.authority = PossibleSendAuthority(self.capacity)

    def reserve(self, identity: str, *, at: int, generation: int) -> bool:
        if generation != self.generation:
            return False
        allowed = self.authority.reserve(identity, at=at)
        if allowed:
            self.owners[identity] = generation
        return allowed

    def handoff(self, identity: str, *, generation: int) -> bool:
        if generation != self.generation or self.owners.get(identity) != generation:
            return False
        if identity in self.handed_off or identity in self.transmitted:
            return False
        self.handed_off.add(identity)
        return True

    def transmit(self, identity: str, *, at: int, generation: int) -> bool:
        """Atomic simulated send-boundary check; real transport lacks this proof."""
        if (generation != self.generation or self.owners.get(identity) != generation
                or identity not in self.handed_off or identity in self.transmitted):
            return False
        self.transmitted.add(identity)
        self.handed_off.remove(identity)
        self.authority.confirm_send(identity, sent_at=at)
        return True

    def crash_and_fence(self) -> int:
        """Simulate an *atomic* fencing event, not an actual host/network fence.

        Unresolved attempts stay charged, including those handed to transport.
        """
        self.generation += 1
        return self.generation

    def timeout(self, identity: str) -> None:
        self.authority.ambiguous_timeout(identity)

    def burden(self, *, at: int) -> int:
        return self.authority.burden(at)
