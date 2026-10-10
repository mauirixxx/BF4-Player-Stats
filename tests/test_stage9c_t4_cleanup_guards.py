"""Offline SQL guard tests with deterministic fake query results; no DB writes."""
from types import SimpleNamespace as Row
import pytest
from scripts.phase5b_stage9c_t4_cleanup_guards import refuse_foreign_references

class Result:
    def __init__(self, n): self.n=n
    def scalar_one(self): return self.n

class FakeConnection:
    def __init__(self, counts): self.counts=iter(counts); self.queries=[]
    def execute(self, query, params):
        sql=str(query)
        assert sql.lstrip().upper().startswith("SELECT")
        self.queries.append((sql, params))
        return Result(next(self.counts))

def fixture():
    return [Row(collector_uuid=None)], [Row(collector_uuid="owner")]

def test_clean_references():
    conn=FakeConnection([0]*14)
    jobs, owners=fixture()
    refuse_foreign_references(conn,"stage9c_t4_test",jobs,owners)
    assert len(conn.queries)==14

@pytest.mark.parametrize("counts,fragment",[
    ([1],"unmarked fixture-linked events"),
    ([0,1],"unrelated jobs"),
    ([0,0,1],"marked events linked to foreign identities"),
])
def test_refuse_foreign_rows(counts,fragment):
    conn=FakeConnection(counts)
    jobs,owners=fixture()
    with pytest.raises(RuntimeError,match=fragment):
        refuse_foreign_references(conn,"stage9c_t4_test",jobs,owners)

def test_refuse_foreign_collector_owner():
    conn=FakeConnection([0])
    jobs=[Row(collector_uuid="outsider")]
    owners=[Row(collector_uuid="owner")]
    with pytest.raises(RuntimeError,match="foreign collector"):
        refuse_foreign_references(conn,"stage9c_t4_test",jobs,owners)
    assert len(conn.queries)==1

@pytest.mark.parametrize("index,table", list(enumerate((
    "soldier_sources", "soldier_names", "profile_soldiers",
    "detailed_stats_current", "detailed_stats_history",
    "soldier_weapon_stats", "soldier_vehicle_stats", "collection_state",
))))
def test_refuse_dependent_rows(index, table):
    counts = [0] * 11
    counts[3 + index] = 1
    conn = FakeConnection(counts)
    jobs, owners = fixture()
    with pytest.raises(RuntimeError, match=table):
        refuse_foreign_references(conn, "stage9c_t4_test", jobs, owners)
    assert table in str(conn.queries[-1][0])

@pytest.mark.parametrize("offset,fragment", [
    (0, "job/soldier identity mismatches"),
    (1, "collector identity mismatches"),
    (2, "foreign collector current-job references"),
])
def test_refuse_identity_drift(offset, fragment):
    counts = [0] * 14
    counts[11 + offset] = 1
    conn = FakeConnection(counts)
    jobs, owners = fixture()
    with pytest.raises(RuntimeError, match=fragment):
        refuse_foreign_references(conn, "stage9c_t4_test", jobs, owners)
    assert len(conn.queries) == 12 + offset
