"""Exercise the actual SQL claim builder against a deterministic offline queue.

This is NOT PostgreSQL execution: a fake connection interprets the bound
allowed_soldier_ids and returns synthetic rows. Real database concurrency,
SKIP LOCKED, leases and timing remain unverified.
"""
from collections import Counter
from types import SimpleNamespace
from uuid import uuid4

from bf4ps.collection_jobs import claim_next_job
from scripts.stage9c_d2_offline_900_simulation import SITES


class OfflineClaimConnection:
    def __init__(self, jobs):
        self.pending = dict(jobs)
        self.claimed = set()
        self.claim_sql_checks = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            return SimpleNamespace()
        if "WITH durable_attempts AS" in sql:
            return SimpleNamespace(scalar_one=lambda: 0)
        assert "FOR UPDATE SKIP LOCKED" in sql
        assert "soldier_id = ANY(:allowed_soldier_ids)" in sql
        self.claim_sql_checks += 1
        allowed = set(params["allowed_soldier_ids"])
        for job_id, soldier_id in self.pending.items():
            if job_id not in self.claimed and soldier_id in allowed:
                self.claimed.add(job_id)
                result = SimpleNamespace(
                    job_id=job_id, soldier_id=soldier_id, resource="detailed",
                    lane="background", attempt_count=1,
                    collector_uuid=params["collector_uuid"],
                    lease_token=params["lease_token"],
                )
                return SimpleNamespace(one_or_none=lambda: result)
        return SimpleNamespace(one_or_none=lambda: None)


def test_real_claim_sql_builder_900_synthetic_jobs():
    per_site = 300
    ownership = {sid: SITES[(sid - 1) // per_site] for sid in range(1, 901)}
    allowed = {site: [sid for sid, owner in ownership.items() if owner == site]
               for site in SITES}
    conn = OfflineClaimConnection({sid: sid for sid in range(1, 901)})
    collectors = {site: uuid4() for site in SITES}
    counts = Counter()
    for _ in range(300):
        for site in SITES:
            job = claim_next_job(
                conn, collector_uuid=collectors[site],
                allowed_soldier_ids=allowed[site], max_total_attempts=900,
                attempts_after_event_id=0,
                attempt_ceiling_resources=["detailed"],
            )
            assert job is not None
            assert ownership[job.soldier_id] == site
            counts[site] += 1
    assert counts == {site: 300 for site in SITES}
    assert len(conn.claimed) == 900
    assert conn.claim_sql_checks == 900
    for site in SITES:
        assert claim_next_job(conn, collector_uuid=collectors[site],
                              allowed_soldier_ids=allowed[site]) is None
