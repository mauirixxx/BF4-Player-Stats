from dataclasses import replace
from uuid import uuid4

import pytest

from bf4ps.collection_jobs import ClaimedJob, claim_next_job, enqueue_job


def test_enqueue_rejects_unknown_resource():
    with pytest.raises(ValueError, match="unsupported resource"):
        enqueue_job(None, soldier_id=1, resource="bogus")  # type: ignore[arg-type]


def test_enqueue_rejects_unknown_lane():
    with pytest.raises(ValueError, match="unsupported lane"):
        enqueue_job(None, soldier_id=1, resource="detailed", lane="bogus")  # type: ignore[arg-type]


def test_enqueue_rejects_unknown_priority_class():
    with pytest.raises(ValueError, match="unsupported priority class"):
        enqueue_job(None, soldier_id=1, resource="detailed", priority_class="bogus")  # type: ignore[arg-type]


def test_claim_rejects_empty_explicit_cohort():
    with pytest.raises(ValueError, match="must not be empty"):
        claim_next_job(None, collector_uuid=uuid4(), allowed_soldier_ids=[])  # type: ignore[arg-type]


def test_claim_rejects_nonpositive_cohort_id():
    with pytest.raises(ValueError, match="only positive IDs"):
        claim_next_job(None, collector_uuid=uuid4(), allowed_soldier_ids=[1, 0])  # type: ignore[arg-type]


def test_claim_rejects_nonpositive_global_ceiling():
    with pytest.raises(ValueError, match="max_total_attempts must be positive"):
        claim_next_job(
            None,  # type: ignore[arg-type]
            collector_uuid=uuid4(),
            allowed_soldier_ids=[1],
            max_total_attempts=0,
        )


def test_claim_requires_cohort_for_global_ceiling():
    with pytest.raises(ValueError, match="requires allowed_soldier_ids"):
        claim_next_job(None, collector_uuid=uuid4(), max_total_attempts=120)  # type: ignore[arg-type]


def test_claimed_job_token_is_part_of_ownership_identity():
    job = ClaimedJob(
        job_id=7,
        soldier_id=11,
        resource="detailed",
        lane="background",
        attempt_count=1,
        collector_uuid=uuid4(),
        lease_token=uuid4(),
    )
    stale = replace(job, lease_token=uuid4())
    assert stale.job_id == job.job_id
    assert stale.collector_uuid == job.collector_uuid
    assert stale.lease_token != job.lease_token


def test_claim_rejects_empty_attempt_ceiling_resources():
    with pytest.raises(ValueError, match="attempt_ceiling_resources must not be empty"):
        claim_next_job(
            None,  # type: ignore[arg-type]
            collector_uuid=uuid4(),
            allowed_soldier_ids=[1],
            max_total_attempts=27,
            attempt_ceiling_resources=[],
        )


def test_claim_rejects_unknown_attempt_ceiling_resource():
    with pytest.raises(ValueError, match="unsupported attempt ceiling resources"):
        claim_next_job(
            None,  # type: ignore[arg-type]
            collector_uuid=uuid4(),
            allowed_soldier_ids=[1],
            max_total_attempts=27,
            attempt_ceiling_resources=["detailed", "bogus"],
        )


def test_claim_requires_ceiling_when_attempt_ceiling_resources_supplied():
    with pytest.raises(ValueError, match="attempt_ceiling_resources requires max_total_attempts"):
        claim_next_job(
            None,  # type: ignore[arg-type]
            collector_uuid=uuid4(),
            allowed_soldier_ids=[1],
            attempt_ceiling_resources=["detailed", "weapons", "vehicles"],
        )
