"""Queue a Battlelog soldier URL for asynchronous verification.

The website calls a restricted SQL boundary; only a trusted backend worker
may use this writer-side helper. No HTTP is performed here.
"""
from sqlalchemy import text
from bf4ps.manual_battlelog_url import parse_battlelog_soldier_url


def enqueue_soldier_verification(conn, url: str) -> int:
    soldier = parse_battlelog_soldier_url(url)
    return int(conn.execute(text("""
        INSERT INTO manual_soldier_verifications
            (persona_id, platform, submitted_url, status, submitted_at)
        VALUES (:persona_id, :platform, :url, 'pending', now())
        ON CONFLICT (persona_id, platform) DO UPDATE
        SET submitted_url = EXCLUDED.submitted_url,
            submitted_at = CASE
                WHEN manual_soldier_verifications.status = 'rejected'
                THEN now() ELSE manual_soldier_verifications.submitted_at END,
            status = CASE
                WHEN manual_soldier_verifications.status = 'rejected'
                THEN 'pending' ELSE manual_soldier_verifications.status END
        RETURNING verification_id
    """), {"persona_id": soldier.persona_id,
           "platform": soldier.platform, "url": url}).scalar_one())
