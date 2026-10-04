"""Live end-to-end validation of BF4PS detailed collection on all platforms."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job

COLLECTOR_NAME = "phase1-multiplatform-cohort"
HOSTNAME = "tcou"
EGRESS_KEY = "phase1-multiplatform-cohort-tcou"
REASON = "phase1_multiplatform_cohort"


@dataclass(frozen=True)
class CohortSoldier:
    name: str
    persona_id: int
    platform: str


COHORT = (
    CohortSoldier("mauirixxx", 236753552, "pc"),
    CohortSoldier("xSilverMystx", 303498475, "ps4"),
    CohortSoldier("S0UL OF STEEL", 928420744, "xboxone"),
)


def main() -> None:
    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("BF4PS_DATABASE_URL is required")

    engine = create_engine(database_url)
    collector_uuid = uuid4()

    print("===== BF4PS PHASE 1 MULTI-PLATFORM COHORT =====")
    print()

    with engine.begin() as conn:
        database_name = conn.execute(text("SELECT current_database()")).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()

        if "test" not in database_name.lower():
            raise SystemExit(f"REFUSING TO RUN against non-test database: {database_name}")
        if recovery:
            raise SystemExit("REFUSING TO RUN against a PostgreSQL recovery node")

        resolved: list[tuple[CohortSoldier, int, str]] = []
        for subject in COHORT:
            soldier = conn.execute(
                text(
                    """
                    SELECT soldier_id, current_name
                    FROM soldiers
                    WHERE persona_id = :persona_id
                      AND platform = :platform
                    """
                ),
                {"persona_id": subject.persona_id, "platform": subject.platform},
            ).mappings().one_or_none()
            if soldier is None:
                raise SystemExit(
                    f"Cohort soldier is not present in BF4PS test database: "
                    f"{subject.name} ({subject.persona_id}, {subject.platform})"
                )

            soldier_id = int(soldier["soldier_id"])
            existing = conn.execute(
                text(
                    """
                    SELECT job_id, status, reason
                    FROM collection_jobs
                    WHERE soldier_id = :soldier_id
                      AND resource = 'detailed'
                    """
                ),
                {"soldier_id": soldier_id},
            ).mappings().one_or_none()
            if existing is not None:
                raise SystemExit(
                    f"REFUSING TO RUN: soldier {soldier_id} already has detailed work: "
                    f"job={existing['job_id']} status={existing['status']} reason={existing['reason']}"
                )
            resolved.append((subject, soldier_id, str(soldier["current_name"])))

        conn.execute(
            text(
                """
                INSERT INTO collectors (
                    collector_uuid, collector_name, hostname, lane, egress_key,
                    enabled, drained, heartbeat_state
                ) VALUES (
                    :collector_uuid, :collector_name, :hostname, 'background',
                    :egress_key, true, false, 'healthy'
                )
                """
            ),
            {
                "collector_uuid": collector_uuid,
                "collector_name": COLLECTOR_NAME,
                "hostname": HOSTNAME,
                "egress_key": EGRESS_KEY,
            },
        )

        jobs: list[tuple[CohortSoldier, int, str, int]] = []
        for subject, soldier_id, current_name in resolved:
            job_id = enqueue_job(
                conn,
                soldier_id=soldier_id,
                resource="detailed",
                lane="background",
                priority_class="interactive",
                reason=REASON,
                priority_value=1000,
            )
            jobs.append((subject, soldier_id, current_name, job_id))

    print(f"database:       {database_name}")
    print(f"recovery:       {recovery}")
    print(f"collector_uuid: {collector_uuid}")
    print(f"egress_key:     {EGRESS_KEY}")
    print(f"cohort size:    {len(jobs)}")
    print()

    identity = CollectorIdentity(
        collector_uuid=collector_uuid,
        collector_name=COLLECTOR_NAME,
        hostname=HOSTNAME,
        egress_key=EGRESS_KEY,
    )

    results_by_job = {}
    for index in range(len(jobs)):
        print(f"Issuing collector invocation {index + 1} of {len(jobs)}...")
        result = collect_one_detailed_job(
            engine,
            identity=identity,
            request_interval_seconds=2.0,
            lease_seconds=120,
            timeout_seconds=15.0,
        )
        if result is None:
            raise AssertionError(f"cohort invocation {index + 1} did not claim a job")
        if result.job_id in results_by_job:
            raise AssertionError(f"job {result.job_id} was collected more than once")
        results_by_job[result.job_id] = result

    expected_job_ids = {job_id for _, _, _, job_id in jobs}
    if set(results_by_job) != expected_job_ids:
        raise AssertionError(
            f"collected jobs do not match cohort: expected={sorted(expected_job_ids)} "
            f"actual={sorted(results_by_job)}"
        )

    print()
    print("===== PLATFORM RESULTS =====")

    with engine.begin() as conn:
        for subject, soldier_id, current_name, job_id in jobs:
            result = results_by_job[job_id]
            current = conn.execute(
                text("SELECT * FROM detailed_stats_current WHERE soldier_id = :soldier_id"),
                {"soldier_id": soldier_id},
            ).mappings().one_or_none()
            history_count = conn.execute(
                text("SELECT COUNT(*) FROM detailed_stats_history WHERE soldier_id = :soldier_id"),
                {"soldier_id": soldier_id},
            ).scalar_one()
            state = conn.execute(
                text(
                    """
                    SELECT detailed_state
                    FROM collection_state
                    WHERE soldier_id = :soldier_id
                    """
                ),
                {"soldier_id": soldier_id},
            ).mappings().one_or_none()
            event = conn.execute(
                text(
                    """
                    SELECT event_id, event_type, result, http_status
                    FROM collection_events
                    WHERE job_id = :job_id
                    ORDER BY event_id DESC
                    LIMIT 1
                    """
                ),
                {"job_id": job_id},
            ).mappings().one_or_none()
            remaining_job = conn.execute(
                text("SELECT COUNT(*) FROM collection_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            ).scalar_one()

            if current is None:
                raise AssertionError(f"{subject.platform}: current stats were not written")
            if history_count < 1:
                raise AssertionError(f"{subject.platform}: history snapshot is missing")
            if state is None or state["detailed_state"] != "success":
                raise AssertionError(f"{subject.platform}: collection state is not success")
            if event is None or event["event_type"] != "collection_success" or event["result"] != "success":
                raise AssertionError(f"{subject.platform}: success event is missing")
            if event["http_status"] != 200:
                raise AssertionError(f"{subject.platform}: expected HTTP 200, got {event['http_status']}")
            if remaining_job != 0:
                raise AssertionError(f"{subject.platform}: completed queue job still exists")

            print(
                f"{subject.platform:8} {current_name!r:20} "
                f"persona={subject.persona_id:<12} job={job_id:<6} "
                f"http=200 history_appended={result.history_appended} "
                f"history_rows={history_count} duration_ms={result.duration_ms}"
            )
            print(
                f"         rank={current['rank']} time={current['time_played_seconds']} "
                f"score={current['total_score']} kills={current['kills']} deaths={current['deaths']}"
            )

        remaining_cohort_jobs = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE reason = :reason
                """
            ),
            {"reason": REASON},
        ).scalar_one()
        if remaining_cohort_jobs != 0:
            raise AssertionError(f"{remaining_cohort_jobs} cohort queue job(s) remain")

        gate_deleted = conn.execute(
            text("DELETE FROM request_gates WHERE egress_key = :egress_key"),
            {"egress_key": EGRESS_KEY},
        ).rowcount
        collector_deleted = conn.execute(
            text("DELETE FROM collectors WHERE collector_uuid = :collector_uuid"),
            {"collector_uuid": collector_uuid},
        ).rowcount

    print()
    print("===== DATABASE VALIDATION =====")
    print(f"all platforms successful: PASS")
    print(f"all queue jobs finalized: PASS")
    print(f"gate cleanup:             {gate_deleted}")
    print(f"collector cleanup:        {collector_deleted}")
    print()
    print("Cohort statistics/history/state/events were intentionally retained.")
    print()
    print("BF4PS PHASE 1 MULTI-PLATFORM COHORT: PASS")


if __name__ == "__main__":
    main()
