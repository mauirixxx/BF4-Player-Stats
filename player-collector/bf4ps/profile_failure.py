"""Profile retry handling under the same job fence as other resources."""
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Connection
from bf4ps.collection_jobs import ClaimedJob

@dataclass(frozen=True)
class ProfileFailure:
    error_class: str
    message: str
    http_status: int | None = None

def persist_profile_failure(conn: Connection, *, job: ClaimedJob, failure: ProfileFailure,
                            attempted_at: datetime, persona_id: int, platform: str,
                            collector_name: str, hostname: str, egress_key: str,
                            duration_ms: int, retry_after_seconds: int) -> None:
    if job.resource != "profile" or retry_after_seconds < 0:
        raise ValueError("invalid profile retry")
    p = dict(job_id=job.job_id, soldier_id=job.soldier_id,
             collector_uuid=job.collector_uuid, lease_token=job.lease_token)
    owned = conn.execute(text("""
        SELECT 1 FROM collection_jobs WHERE job_id=:job_id AND soldier_id=:soldier_id
        AND resource='profile' AND status='running' AND collector_uuid=:collector_uuid
        AND lease_token=:lease_token AND lease_expires_at > now() FOR UPDATE
    """), p).one_or_none()
    if owned is None:
        raise RuntimeError("profile failure rejected: lease ownership lost")
    conn.execute(text("""
        UPDATE collection_state SET profile_state='temporary_failure',
          profile_last_attempt_at=:at,
          profile_next_due_at=:at + (:delay * interval '1 second'),
          profile_consecutive_failures=profile_consecutive_failures+1,
          profile_last_error_class=:error_class, profile_last_error_message=:message,
          updated_at=now() WHERE soldier_id=:soldier_id
    """), dict(soldier_id=job.soldier_id, at=attempted_at, delay=retry_after_seconds,
               error_class=failure.error_class, message=failure.message[:2000]))
    conn.execute(text("""
        INSERT INTO collection_events
          (collector_uuid, collector_name_snapshot, hostname_snapshot, egress_key_snapshot,
           job_id, soldier_id, persona_id, platform, resource, lane, event_type,
           attempt_number, result, duration_ms, http_status, error_class, error_message,
           lease_token, metadata)
        VALUES (:collector_uuid, :collector_name, :hostname, :egress_key,
          :job_id, :soldier_id, :persona_id, :platform, 'profile', :lane,
          'collection_failure', :attempt, 'temporary_failure', :duration_ms,
          :http_status, :error_class, :message, :lease_token,
          jsonb_build_object('retry_after_seconds', :delay))
    """), dict(**p, collector_name=collector_name, hostname=hostname,
               egress_key=egress_key, persona_id=persona_id, platform=platform,
               lane=job.lane, attempt=job.attempt_count, duration_ms=duration_ms,
               http_status=failure.http_status, error_class=failure.error_class,
               message=failure.message[:2000], delay=retry_after_seconds))
    released = conn.execute(text("""
        UPDATE collection_jobs SET status='pending',
          eligible_at=:at + (:delay * interval '1 second'),
          collector_uuid=NULL, lease_token=NULL, claimed_at=NULL, started_at=NULL,
          lease_expires_at=NULL, last_error_class=:error_class,
          last_error_at=:at, updated_at=now()
        WHERE job_id=:job_id AND soldier_id=:soldier_id AND resource='profile'
          AND status='running' AND collector_uuid=:collector_uuid
          AND lease_token=:lease_token AND lease_expires_at > now()
    """), dict(**p, at=attempted_at, delay=retry_after_seconds,
               error_class=failure.error_class))
    if released.rowcount != 1:
        raise RuntimeError("profile failure rejected: retry release lost lease")
