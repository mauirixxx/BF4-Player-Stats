"""Stable production collector identities for BF4PS background collection."""

from __future__ import annotations

from dataclasses import dataclass
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
RESOURCES = ("detailed", "weapons", "vehicles")
REQUEST_INTERVAL_SECONDS = 5.0
LEASE_SECONDS = 120
SOFTWARE_VERSION = "phase5b-production"
