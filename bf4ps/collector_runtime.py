"""Phase 2 single-node collector registry and heartbeat primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.detailed_collector import CollectorIdentity


@dataclass(frozen=True)
class CollectorControl:
    enabled: bool
    drained: bool

    @property
    def may_claim(self) -> bool:
        return self.enabled and not self.drained


def _validate_identity(identity: CollectorIdentity) -> None:
    if not identity.collector_name.strip():
        raise ValueError("collector_name must be non-empty")
    if not identity.hostname.strip():
        raise ValueError("hostname must be non-empty")
    if not identity.egress_key.strip():
        raise ValueError("egress_key must be non-empty")
    if identity.lane not in {"background", "interactive"}:
        raise ValueError("collector lane must be background or interactive")


def register_collector(
    conn: Connection,
    *,
    identity: CollectorIdentity,
    software_version: str | None = None,
) -> CollectorControl:
    """Register/refresh one stable collector identity without overriding controls.

    Existing ``enabled`` and ``drained`` values are operator-owned and are
    deliberately preserved on restart.  Identity drift for an existing UUID is
    rejected rather than silently rewriting historical operational identity.
    """
    _validate_identity(identity)
    now = datetime.now(timezone.utc)

    existing = conn.execute(
        text(
            """
            SELECT collector_name, hostname, lane, egress_key, enabled, drained,
                   retired_at
            FROM collectors
            WHERE collector_uuid = :collector_uuid
            FOR UPDATE
            """
        ),
        {"collector_uuid": identity.collector_uuid},
    ).mappings().one_or_none()

    if existing is None:
        row = conn.execute(
            text(
                """
                INSERT INTO collectors (
                    collector_uuid, collector_name, hostname, lane, egress_key,
                    enabled, drained, software_version, started_at,
                    last_heartbeat_at, heartbeat_state, heartbeat_lost_at,
                    current_job_id, updated_at
                )
                VALUES (
                    :collector_uuid, :collector_name, :hostname, :lane, :egress_key,
                    true, false, :software_version, :now,
                    :now, 'healthy', NULL, NULL, :now
                )
                RETURNING enabled, drained
                """
            ),
            {
                "collector_uuid": identity.collector_uuid,
                "collector_name": identity.collector_name,
                "hostname": identity.hostname,
                "lane": identity.lane,
                "egress_key": identity.egress_key,
                "software_version": software_version,
                "now": now,
            },
        ).mappings().one()
        return CollectorControl(bool(row["enabled"]), bool(row["drained"]))

    if existing["retired_at"] is not None:
        raise RuntimeError("collector identity is retired and cannot be restarted")

    configured = (
        identity.collector_name,
        identity.hostname,
        identity.lane,
        identity.egress_key,
    )
    registered = (
        existing["collector_name"],
        existing["hostname"],
        existing["lane"],
        existing["egress_key"],
    )
    if configured != registered:
        raise RuntimeError(
            "collector identity configuration does not match registered UUID"
        )

    conn.execute(
        text(
            """
            UPDATE collectors
            SET software_version = :software_version,
                started_at = :now,
                last_heartbeat_at = :now,
                heartbeat_state = 'healthy',
                heartbeat_lost_at = NULL,
                current_job_id = NULL,
                updated_at = :now
            WHERE collector_uuid = :collector_uuid
            """
        ),
        {
            "collector_uuid": identity.collector_uuid,
            "software_version": software_version,
            "now": now,
        },
    )
    return CollectorControl(bool(existing["enabled"]), bool(existing["drained"]))


def heartbeat_collector(
    conn: Connection,
    *,
    collector_uuid: UUID,
    software_version: str | None = None,
) -> CollectorControl:
    """Refresh liveness and return current operator control state."""
    row = conn.execute(
        text(
            """
            UPDATE collectors
            SET last_heartbeat_at = now(),
                heartbeat_state = 'healthy',
                heartbeat_lost_at = NULL,
                software_version = COALESCE(:software_version, software_version),
                updated_at = now()
            WHERE collector_uuid = :collector_uuid
              AND retired_at IS NULL
            RETURNING enabled, drained
            """
        ),
        {
            "collector_uuid": collector_uuid,
            "software_version": software_version,
        },
    ).mappings().one_or_none()
    if row is None:
        raise RuntimeError("collector is missing or retired")
    return CollectorControl(bool(row["enabled"]), bool(row["drained"]))


def stop_collector(conn: Connection, *, collector_uuid: UUID) -> bool:
    """Best-effort clean-stop marker; controls remain operator-owned."""
    result = conn.execute(
        text(
            """
            UPDATE collectors
            SET heartbeat_state = 'unknown',
                current_job_id = NULL,
                updated_at = now()
            WHERE collector_uuid = :collector_uuid
              AND retired_at IS NULL
            """
        ),
        {"collector_uuid": collector_uuid},
    )
    return result.rowcount == 1
