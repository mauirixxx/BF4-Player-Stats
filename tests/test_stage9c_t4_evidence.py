"""Offline evidence comparisons; no database access."""
from copy import deepcopy
import pytest
from scripts.phase5b_stage9c_t4_evidence import compare

def evidence():
    return {"format":1,"marker":"stage9c_t4_example","database":"scratch",
            "revision":"0004_stage9c_supervision_runs",
            "tables":{"collection_events":{"rows":1295,"sha256":"a"*64},
                      "collection_jobs":{"rows":3,"sha256":"b"*64}},
            "marked_event_counts":{"collection_attempt_started":1295}}

def test_identical_evidence():
    assert compare(evidence(),deepcopy(evidence()))

@pytest.mark.parametrize("mutate",[
    lambda d:d["tables"]["collection_events"].update(rows=1294),
    lambda d:d["tables"]["collection_jobs"].update(sha256="c"*64),
    lambda d:d["marked_event_counts"].update(collection_attempt_started=1294),
    lambda d:d.update(marker="stage9c_t4_wrong"),
    lambda d:d.update(revision="wrong"),
])
def test_evidence_mismatch(mutate):
    after=deepcopy(evidence())
    mutate(after)
    with pytest.raises(RuntimeError,match="evidence mismatch"):
        compare(evidence(),after)
