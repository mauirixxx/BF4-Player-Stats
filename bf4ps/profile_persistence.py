"""Atomic profile success persistence; follows the existing leased-job contract."""
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Connection
from bf4ps.collection_jobs import ClaimedJob
from bf4ps.battlelog_profile import ProfileObservation

def persist_profile_success(conn: Connection, *, job: ClaimedJob,
                            observation: ProfileObservation, observed_at: datetime,
                            persona_id: int, platform: str, collector_name: str,
                            hostname: str, egress_key: str, duration_ms: int) -> int:
    if job.resource != "profile":
        raise ValueError("requires profile job")
    if observation.access_state not in ("public_country", "public_no_country", "friends_only"):
        raise ValueError("unsupported successful profile observation")
    if observation.country_code is not None and (len(observation.country_code) != 2 or not observation.country_code.isalpha()):
        raise ValueError("invalid country code")
    p = dict(job_id=job.job_id, soldier_id=job.soldier_id,
             collector_uuid=job.collector_uuid, lease_token=job.lease_token)
    owned = conn.execute(text("""
        SELECT 1 FROM collection_jobs WHERE job_id=:job_id AND soldier_id=:soldier_id
        AND resource='profile' AND status='running' AND collector_uuid=:collector_uuid
        AND lease_token=:lease_token AND lease_expires_at > now() FOR UPDATE
    """), p).one_or_none()
    if owned is None:
        raise RuntimeError("profile success rejected: lease ownership lost")
    profile_id = conn.execute(text("""
        INSERT INTO battlelog_profiles
          (battlelog_username, country_code, country_name, access_state,
           last_checked_at, last_success_at, last_error)
        VALUES (:username, :code, :country, :state, :at, :at, NULL)
        ON CONFLICT (lower(battlelog_username)) DO UPDATE SET
          country_code=EXCLUDED.country_code, country_name=EXCLUDED.country_name,
          access_state=EXCLUDED.access_state, last_checked_at=EXCLUDED.last_checked_at,
          last_success_at=EXCLUDED.last_success_at, last_error=NULL, updated_at=now()
        RETURNING profile_id
    """), dict(username=observation.username, code=observation.country_code,
               country=observation.country_name, state=observation.access_state,
               at=observed_at)).scalar_one()
    conn.execute(text("""
        INSERT INTO profile_soldiers (profile_id, soldier_id, first_seen_at, last_seen_at)
        VALUES (:profile_id, :soldier_id, :at, :at)
        ON CONFLICT (profile_id, soldier_id) DO UPDATE SET last_seen_at=EXCLUDED.last_seen_at
    """), dict(profile_id=profile_id, soldier_id=job.soldier_id, at=observed_at))
    conn.execute(text("""
        UPDATE collection_state SET profile_state='success',
          profile_last_attempt_at=:at, profile_last_success_at=:at,
          profile_next_due_at=:at + interval '30 days',
          profile_consecutive_failures=0, profile_last_error_class=NULL,
          profile_last_error_message=NULL, updated_at=now()
        WHERE soldier_id=:soldier_id
    """), dict(at=observed_at, soldier_id=job.soldier_id))
    conn.execute(text("""
        INSERT INTO collection_events
          (collector_uuid, collector_name_snapshot, hostname_snapshot, egress_key_snapshot,
           job_id, soldier_id, persona_id, platform, resource, lane, event_type,
           attempt_number, result, duration_ms, http_status, lease_token, metadata)
        VALUES (:collector_uuid, :collector_name, :hostname, :egress_key,
          :job_id, :soldier_id, :persona_id, :platform, 'profile', :lane,
          'collection_success', :attempt, 'success', :duration_ms, 200, :lease_token,
          jsonb_build_object('profile_id', CAST(:profile_id AS bigint), 'access_state', CAST(:state AS text)))
    """), dict(**p, collector_name=collector_name, hostname=hostname,
               egress_key=egress_key, persona_id=persona_id, platform=platform,
               lane=job.lane, attempt=job.attempt_count, duration_ms=duration_ms,
               profile_id=profile_id, state=observation.access_state))
    result = conn.execute(text("""
        DELETE FROM collection_jobs WHERE job_id=:job_id AND soldier_id=:soldier_id
        AND resource='profile' AND status='running' AND collector_uuid=:collector_uuid
        AND lease_token=:lease_token AND lease_expires_at > now()
    """), p)
    if result.rowcount != 1:
        raise RuntimeError("profile success rejected: finalization lost lease")
    return int(profile_id)
