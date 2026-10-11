"""Offline SQL contract tests for remote synthetic D2 state reconstruction."""
from unittest.mock import Mock

import pytest

from scripts.phase5b_three_site_manifest import RunManifest
from scripts.phase5b_three_site_remote_state import reconstruct


def manifest():
    return RunManifest.build(run_id="d2test_under_score",
                             distribution={"tcou": 1, "kah-01": 1, "hnl-01": 1},
                             job_count=2, claim_limit_per_worker=1, lease_seconds=30)


def test_reconstruct_two_rows_and_literal_prefix():
    m = manifest()
    conn = Mock()
    conn.execute.return_value.all.return_value = [
        Mock(soldier_id=10, job_id=20), Mock(soldier_id=11, job_id=21)]
    state = reconstruct(conn, m)
    assert state["soldier_ids"] == [10, 11]
    assert state["job_ids"] == [20, 21]
    assert state["manifest_sha256"] == m.report()["sha256"]
    sql, params = conn.execute.call_args.args
    assert "left(s.current_name, length(:prefix)) = :prefix" in str(sql)
    assert params["prefix"] == "synthetic-three-site-d2test_under_score-"
    assert "%" not in params["prefix"]


@pytest.mark.parametrize("count", [0, 1, 3])
def test_reject_incomplete_or_extra_rows(count):
    m = manifest()
    conn = Mock()
    conn.execute.return_value.all.return_value = [
        Mock(soldier_id=i + 10, job_id=i + 20) for i in range(count)]
    with pytest.raises(RuntimeError, match="incomplete"):
        reconstruct(conn, m)
