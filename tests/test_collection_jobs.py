from dataclasses import replace
from uuid import uuid4

import pytest

from bf4ps.collection_jobs import ClaimedJob, enqueue_job


def test_enqueue_rejects_unknown_resource():
    with pytest.raises(ValueError, match="unsupported resource"):
        enqueue_job(None, soldier_id=1, resource="bogus")  # type: ignore[arg-type]


def test_enqueue_rejects_unknown_lane():
    with pytest.raises(ValueError, match="unsupported lane"):
        enqueue_job(None, soldier_id=1, resource="detailed", lane="bogus")  # type: ignore[arg-type]


def test_enqueue_rejects_unknown_priority_class():
    with pytest.raises(ValueError, match="unsupported priority class"):
        enqueue_job(None, soldier_id=1, resource="detailed", priority_class="bogus")  # type: ignore[arg-type]


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
