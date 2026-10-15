"""Trusted manual soldier ingestion, deliberately not exposed to the website login.

Only a server-side Battlelog verifier may supply VerifiedSoldier. A parsed URL
is not proof of existence. Run in a privileged backend transaction, never
with the restricted manual API database role.
"""
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.manual_battlelog_url import parse_battlelog_soldier_url
from bf4ps.manual_request_admission import admit_registered_soldier


@dataclass(frozen=True)
class VerifiedSoldier:
    persona_id: int
    platform: str
    current_name: str


def insert_verified_manual_soldier(conn: Connection, *, url: str, verified: VerifiedSoldier):
    """Persist a verified soldier and request initial collection atomically.

    Caller must independently obtain 'verified' from trusted Battlelog evidence,
    not from URL text or user-submitted fields. Caller owns transaction.
    """
    parsed = parse_battlelog_soldier_url(url)
    if (verified.persona_id != parsed.persona_id or
            verified.platform != parsed.platform or
            not isinstance(verified.current_name, str) or
            not verified.current_name.strip() or
            len(verified.current_name) > 255):
        raise ValueError("Battlelog identity verification mismatch")
    name = verified.current_name.strip()
    soldier_id = conn.execute(text("""
        INSERT INTO soldiers (persona_id, platform, current_name, first_seen_at, last_seen_at)
        VALUES (:persona_id, :platform, :name, now(), now())
        ON CONFLICT (persona_id, platform) DO UPDATE SET
            updated_at = soldiers.updated_at
        RETURNING soldier_id
    """), {"persona_id": parsed.persona_id, "platform": parsed.platform,
           "name": name}).scalar_one()
    conn.execute(text("""
        INSERT INTO soldier_sources (soldier_id, source_type, first_seen_at, last_seen_at)
        VALUES (:soldier_id, 'manual', now(), now())
        ON CONFLICT (soldier_id, source_type) DO UPDATE
        SET last_seen_at = GREATEST(soldier_sources.last_seen_at, EXCLUDED.last_seen_at)
    """), {"soldier_id": soldier_id})
    conn.execute(text("""
        INSERT INTO soldier_names (soldier_id, name, first_seen_at, last_seen_at)
        VALUES (:soldier_id, :name, now(), now())
        ON CONFLICT (soldier_id, name) DO NOTHING
    """), {"soldier_id": soldier_id, "name": name})
    conn.execute(text("""
        INSERT INTO collection_state (soldier_id)
        VALUES (:soldier_id) ON CONFLICT (soldier_id) DO NOTHING
    """), {"soldier_id": soldier_id})
    admission = admit_registered_soldier(conn, soldier_id=int(soldier_id), kind="add")
    return int(soldier_id), admission
