"""Offline counterexamples to check-then-send and gateway failover.

No real sockets, clocks, DB writes or HTTP. The schedules are adversarial
logical events, not a claim about a particular OS or transport implementation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransportSchedule:
    check_at: int
    fence_at: int
    send_at: int

    def check_was_valid(self) -> bool:
        return self.check_at < self.fence_at

    def send_after_fence(self) -> bool:
        return self.send_at > self.fence_at


def post_check_pause_counterexample(*, pause_seconds: int = 3602) -> TransportSchedule:
    """An authorization check succeeds; send occurs after ownership fencing."""
    if pause_seconds < 2:
        raise ValueError("pause_seconds must be >= 2")
    return TransportSchedule(check_at=0, fence_at=1, send_at=pause_seconds)


@dataclass
class FencingScenario:
    """An ideal logical fence does not retract an already submitted write."""

    old_generation: int = 1
    active_generation: int = 1
    old_write_queued: bool = False
    old_write_transmitted: bool = False

    def submit_old_write(self) -> None:
        if self.old_generation != self.active_generation:
            raise ValueError("old generation already fenced")
        self.old_write_queued = True

    def fence_old_generation(self) -> None:
        self.active_generation += 1

    def drain_queued_write(self) -> bool:
        """Models a buffered write that may outlive a control-plane fence."""
        if not self.old_write_queued or self.old_write_transmitted:
            return False
        self.old_write_transmitted = True
        return True


def conservative_fencing_resolution(*, old_write_queued: bool, transport_drained_proven: bool) -> bool:
    """Only permit release when a *separate proof* rules out later sends.

    This function does not generate such a proof; the boolean is an explicit
    external assumption, and cannot be inferred from a generation increment.
    """
    return not old_write_queued or transport_drained_proven
