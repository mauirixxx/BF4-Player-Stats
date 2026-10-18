"""One leased Battlelog profile job; optional enrichment."""
from dataclasses import dataclass
import os
from datetime import datetime, timezone
from time import monotonic, sleep
from typing import Sequence
from sqlalchemy import text
from sqlalchemy.engine import Engine
from bf4ps.battlelog_profile import ProfileFetchError, fetch_profile
from bf4ps.account_resolution import fetch_account_observation, AccountResolutionError
from urllib.error import HTTPError, URLError
from bf4ps.collection_jobs import claim_next_job, mark_job_running
from bf4ps.background_service import claim_production_background_job
from bf4ps.detailed_collector import CollectorIdentity
from bf4ps.profile_failure import ProfileFailure, persist_profile_failure
from bf4ps.profile_persistence import persist_profile_success
from bf4ps.request_gate import reserve_request_slot
from bf4ps.physical_dispatch_gate import authorized_http_attempt
from bf4ps.retry_policy import retry_delay_for_failure

@dataclass(frozen=True)
class CollectedProfileJob:
    job_id: int
    soldier_id: int
    persona_id: int
    platform: str
    profile_id: int
    duration_ms: int

@dataclass(frozen=True)
class FailedProfileJob:
    job_id: int
    soldier_id: int
    persona_id: int
    platform: str
    error_class: str
    http_status: int | None
    retry_after_seconds: int
    duration_ms: int

def collect_one_profile_job(engine: Engine, *, identity: CollectorIdentity,
                            request_interval_seconds: float, lease_seconds: int = 120,
                            timeout_seconds: float = 30.0,
                            allowed_soldier_ids: Sequence[int] | None = None,
                            max_total_attempts: int | None = None,
                            enforce_production_budget: bool = False):
    with engine.begin() as conn:
        kwargs = dict(collector_uuid=identity.collector_uuid, resource="profile",
                      lease_seconds=lease_seconds, allowed_soldier_ids=allowed_soldier_ids,
                      max_total_attempts=max_total_attempts)
        if enforce_production_budget and identity.lane == "background":
            job = claim_production_background_job(conn, **kwargs)
        else:
            job = claim_next_job(conn, lane=identity.lane, **kwargs)
        if job is None:
            return None
        if not mark_job_running(conn, job):
            raise RuntimeError("profile job cannot transition to running")
    with engine.connect() as conn:
        soldier = conn.execute(text("""
            SELECT persona_id, platform, current_name FROM soldiers
            WHERE soldier_id=:soldier_id
        """), dict(soldier_id=job.soldier_id)).one()
    persona_id, platform, username = int(soldier[0]), str(soldier[1]), str(soldier[2])
    def reserve_and_wait():
        with engine.begin() as conn:
            permit = reserve_request_slot(conn, egress_key=identity.egress_key,
                                          interval_seconds=request_interval_seconds)
        if permit.wait_seconds:
            sleep(permit.wait_seconds)

    # Existing successful profile links are an authoritative identity cache.
    # Never infer account names from the soldier's current display name.
    with engine.connect() as conn:
        username = conn.execute(text("""
            SELECT bp.battlelog_username FROM profile_soldiers ps
            JOIN battlelog_profiles bp ON bp.profile_id=ps.profile_id
            WHERE ps.soldier_id=:soldier_id
            ORDER BY ps.last_seen_at DESC LIMIT 1
        """), {"soldier_id": job.soldier_id}).scalar_one_or_none()
    username_was_resolved = username is None
    resolution_error = None
    account_observation = None
    if username is None:
        try:
            reserve_and_wait()
            if enforce_production_budget:
                with authorized_http_attempt(
                    engine, job=job, identity=identity, resource="profile",
                    request_ordinal=1,
                    request_label=f"profile-resolution:{persona_id}:{platform}",
                ):
                    account_observation = fetch_account_observation(str(soldier[2]), persona_id, platform,
                                                      timeout_seconds=timeout_seconds)
            else:
                account_observation = fetch_account_observation(str(soldier[2]), persona_id, platform,
                                                  timeout_seconds=timeout_seconds)
            username = account_observation.username
        except (AccountResolutionError, HTTPError, URLError, TimeoutError, OSError,
                UnicodeDecodeError, ValueError) as exc:
            resolution_error = ProfileFetchError(f"account resolution failed: {exc}")
    # Passive observation only: no extra Battlelog requests, and never break
    # statistics collection if optional platoon persistence is unavailable.
    if account_observation is not None:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO platoon_soldier_discovery
                      (soldier_id,status,attempts,next_attempt_at,last_checked_at,linked_platoon_id,displayed_tag)
                    VALUES (:soldier_id,'complete',0,now(),now(),:linked_platoon_id,:displayed_tag)
                    ON CONFLICT (soldier_id) DO UPDATE SET
                      status='complete',last_checked_at=excluded.last_checked_at,
                      linked_platoon_id=excluded.linked_platoon_id,
                      displayed_tag=excluded.displayed_tag,last_error=NULL
                """), dict(soldier_id=job.soldier_id,
                           linked_platoon_id=account_observation.linked_platoon_id,
                           displayed_tag=account_observation.displayed_tag))
        except Exception:
            # Optional enrichment must never fail an otherwise valid profile job.
            pass
    if resolution_error is None:
        reserve_and_wait()
    with engine.begin() as conn:
        owned = conn.execute(text("""
            SELECT 1 FROM collection_jobs WHERE job_id=:job_id AND soldier_id=:soldier_id
            AND resource='profile' AND status='running' AND collector_uuid=:collector_uuid
            AND lease_token=:lease_token AND lease_expires_at > now() FOR UPDATE
        """), dict(job_id=job.job_id, soldier_id=job.soldier_id,
                   collector_uuid=job.collector_uuid, lease_token=job.lease_token)).one_or_none()
        if owned is None:
            raise RuntimeError("profile attempt rejected: lease lost")
        conn.execute(text("""
            INSERT INTO collection_events
              (collector_uuid, collector_name_snapshot, hostname_snapshot, egress_key_snapshot,
               job_id, soldier_id, persona_id, platform, resource, lane, event_type,
               attempt_number, lease_token, metadata)
            VALUES (:uuid, :name, :host, :egress, :job_id, :soldier_id, :persona,
              :platform, 'profile', :lane, 'collection_attempt_started',
              :attempt, :token, jsonb_build_object('physical_request', true, 'priority_class',
                (SELECT priority_class FROM collection_jobs WHERE job_id=:job_id),
                'retry', (SELECT last_error_at IS NOT NULL FROM collection_jobs WHERE job_id=:job_id)))
        """), dict(uuid=job.collector_uuid, name=identity.collector_name,
                   host=identity.hostname, egress=identity.egress_key,
                   job_id=job.job_id, soldier_id=job.soldier_id,
                   persona=persona_id, platform=platform, lane=job.lane,
                   attempt=job.attempt_count, token=job.lease_token))
    started = monotonic()
    try:
        if resolution_error is not None:
            raise resolution_error
        if enforce_production_budget:
            with authorized_http_attempt(
                engine, job=job, identity=identity, resource="profile",
                request_ordinal=2 if username_was_resolved else 1,
                request_label=f"profile-page:{persona_id}:{platform}:{username}",
            ):
                observation = fetch_profile(username, timeout_seconds=timeout_seconds,
                                            expected_persona_id=persona_id, expected_platform=platform)
        else:
            observation = fetch_profile(username, timeout_seconds=timeout_seconds,
                                        expected_persona_id=persona_id, expected_platform=platform)
    except ProfileFetchError as exc:
        duration_ms = max(0, int((monotonic()-started)*1000))
        with engine.connect() as conn:
            retry = (int(os.environ["BF4PS_PROFILE_DIAGNOSTIC_RETRY_SECONDS"]) if "BF4PS_PROFILE_DIAGNOSTIC_RETRY_SECONDS" in os.environ else retry_delay_for_failure(conn, soldier_id=job.soldier_id, resource="profile"))
        with engine.begin() as conn:
            persist_profile_failure(conn, job=job,
                failure=ProfileFailure("battlelog_profile_fetch", str(exc)),
                attempted_at=datetime.now(timezone.utc), persona_id=persona_id,
                platform=platform, collector_name=identity.collector_name,
                hostname=identity.hostname, egress_key=identity.egress_key,
                duration_ms=duration_ms, retry_after_seconds=retry)
        return FailedProfileJob(job.job_id, job.soldier_id, persona_id, platform,
                                "battlelog_profile_fetch", None, retry, duration_ms)
    duration_ms = max(0, int((monotonic()-started)*1000))
    with engine.begin() as conn:
        profile_id = persist_profile_success(conn, job=job, observation=observation,
            observed_at=datetime.now(timezone.utc), persona_id=persona_id,
            platform=platform, collector_name=identity.collector_name,
            hostname=identity.hostname, egress_key=identity.egress_key,
            duration_ms=duration_ms)
    return CollectedProfileJob(job.job_id, job.soldier_id, persona_id, platform,
                               profile_id, duration_ms)
