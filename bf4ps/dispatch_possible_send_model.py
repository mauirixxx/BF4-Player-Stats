"""Pure offline fail-closed possible-send authority model.

This is a *capacity accounting model*, not a network enforcement proof.
Assumes each attempt can cause at most one physical send and no bypass.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PossibleSendAuthority:
    capacity: int
    # Physical sends proven completed, keyed by unique attempt identity.
    confirmed: dict[str, int] = field(default_factory=dict)
    # Unresolved attempts can still physically send at an arbitrary future time.
    unresolved: set[str] = field(default_factory=set)
    retired: set[str] = field(default_factory=set)

    def _validate(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be positive")

    def burden(self, at: int) -> int:
        self._validate()
        return len(self.unresolved) + sum(at - 3600 < sent <= at for sent in self.confirmed.values())

    def reserve(self, identity: str, *, at: int) -> bool:
        self._validate()
        if not identity or identity in self.confirmed or identity in self.unresolved or identity in self.retired:
            raise ValueError("identity must be fresh")
        if self.burden(at) >= self.capacity:
            return False
        self.unresolved.add(identity)
        return True

    def confirm_send(self, identity: str, *, sent_at: int) -> None:
        if identity not in self.unresolved:
            raise ValueError("unknown or already resolved attempt")
        self.unresolved.remove(identity)
        self.confirmed[identity] = sent_at

    def prove_no_send_possible(self, identity: str) -> None:
        """Only valid with external, rigorous proof of no past/future send.

        A lease expiry, process timeout, or gateway restart is NOT such proof.
        """
        if identity not in self.unresolved:
            raise ValueError("unknown or already resolved attempt")
        self.unresolved.remove(identity)
        self.retired.add(identity)

    def ambiguous_timeout(self, identity: str) -> None:
        if identity not in self.unresolved:
            raise ValueError("unknown attempt")
        # No state transition: still consumes capacity indefinitely.
