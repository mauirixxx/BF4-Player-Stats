"""Stable production collector identities for BF4PS background collection."""

from __future__ import annotations

from dataclasses import dataclass
import os
import socket
from uuid import UUID


@dataclass(frozen=True)
class ProductionHost:
    collector_uuid: UUID
    collector_name: str
    egress_key: str


HOSTS = {
    "hnl-01": ProductionHost(
        UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001"),
        "phase3e-hnl-01",
        "phase3e-hnl-01",
    ),
    "kah-01": ProductionHost(
        UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002"),
        "phase3e-kah-01",
        "phase3e-kah-01",
    ),
    "tcou": ProductionHost(
        UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003"),
        "phase3e-tcou",
        "phase3e-tcou",
    ),
}

COLLECTOR_UUIDS = tuple(host.collector_uuid for host in HOSTS.values())
RESOURCES = ("detailed", "weapons", "vehicles", "profile")
REQUEST_INTERVAL_SECONDS = 4.0
LEASE_SECONDS = 120
SOFTWARE_VERSION = "1.0.0rc1"


def resolve_production_host(*, environ=None, hostname=None):
    """Explicit identity for new hosts; legacy host mapping remains for soak compatibility.

    BF4PS_COLLECTOR_UUID must be stable and unique across the fleet. Egress
    keys are logical request-gate domains, not automatically unique per host.
    """
    env = os.environ if environ is None else environ
    host = (hostname or env.get("BF4PS_HOSTNAME") or socket.gethostname()).split(".", 1)[0]
    if not host.strip():
        raise ValueError("collector hostname must be non-empty")
    configured = (env.get("BF4PS_COLLECTOR_UUID"), env.get("BF4PS_COLLECTOR_NAME"), env.get("BF4PS_EGRESS_KEY"))
    if any(configured):
        if not all(configured):
            raise ValueError("BF4PS_COLLECTOR_UUID, BF4PS_COLLECTOR_NAME and BF4PS_EGRESS_KEY must all be set")
        try:
            uid = UUID(configured[0])
        except (ValueError, AttributeError) as exc:
            raise ValueError("BF4PS_COLLECTOR_UUID must be a valid UUID") from exc
        if uid.int == 0 or any(not value.strip() for value in configured[1:]):
            raise ValueError("Collector UUID must be nonzero and name/egress key nonempty")
        return host, ProductionHost(uid, configured[1].strip(), configured[2].strip())
    legacy = HOSTS.get(host)
    if legacy is None:
        raise ValueError("New hosts require BF4PS_COLLECTOR_UUID, BF4PS_COLLECTOR_NAME, BF4PS_EGRESS_KEY")
    return host, legacy
