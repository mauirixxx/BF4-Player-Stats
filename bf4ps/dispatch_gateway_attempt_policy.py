"""Pure gateway HTTP attempt policy, with no network or database access.

This validates *logical request eligibility only*. It is not a physical-send
limiter or a transport fencing mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RESOURCES = frozenset({"detailed", "weapons", "vehicles"})
PLATFORMS = frozenset({"pc", "ps4", "xboxone"})


@dataclass(frozen=True)
class GatewayRequest:
    attempt_id: str
    resource: str
    platform: str
    persona_id: int
    method: str = "GET"
    follow_redirects: bool = False
    automatic_retries: int = 0


def validate_request(request: GatewayRequest) -> None:
    if not isinstance(request.attempt_id, str) or not request.attempt_id.strip():
        raise ValueError("attempt_id must be nonempty")
    if request.resource not in RESOURCES:
        raise ValueError("resource not allowlisted")
    if request.platform not in PLATFORMS:
        raise ValueError("platform not allowlisted")
    if type(request.persona_id) is not int or request.persona_id <= 0:
        raise ValueError("persona_id must be a positive integer")
    if request.method != "GET":
        raise ValueError("only GET is allowed")
    if request.follow_redirects is not False:
        raise ValueError("automatic redirects forbidden")
    if type(request.automatic_retries) is not int or request.automatic_retries != 0:
        raise ValueError("automatic retries forbidden")


@dataclass
class OfflineAttemptRegistry:
    """A test-only registry, not durable or distributed."""

    reserved: set[str] = field(default_factory=set)
    handed_off: set[str] = field(default_factory=set)

    def reserve(self, request: GatewayRequest) -> bool:
        validate_request(request)
        if request.attempt_id in self.reserved:
            return False
        self.reserved.add(request.attempt_id)
        return True

    def handoff(self, request: GatewayRequest) -> bool:
        validate_request(request)
        if request.attempt_id not in self.reserved:
            return False
        if request.attempt_id in self.handed_off:
            return False
        self.handed_off.add(request.attempt_id)
        return True
