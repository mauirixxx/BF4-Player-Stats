from types import SimpleNamespace
import pytest
from bf4ps.manual_job_enqueue import insert_missing_manual_jobs

class Conn:
    def __init__(self): self.calls=[]
    def execute(self, sql, params):
        self.calls.append((str(sql),params))
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ['profile']))


def test_insert_only_missing_without_touching_existing_lease():
    c=Conn()
    result=insert_missing_manual_jobs(c,soldier_id=42,resources=('weapons','profile'))
    assert result == ('profile',)
    sql,params=c.calls[0]
    assert 'ON CONFLICT (soldier_id, resource) DO NOTHING' in sql
    assert 'UPDATE collection_jobs' not in sql
    assert "'background'" in sql and "'interactive'" in sql
    assert params['resources']==['weapons','profile']


def test_empty_is_noop():
    c=Conn()
    assert insert_missing_manual_jobs(c,soldier_id=1,resources=())==()
    assert c.calls==[]

@pytest.mark.parametrize('soldier_id,resources', [(0,('profile',)),(True,('profile',)),(1,('bad',)),(1,('profile','profile'))])
def test_invalid(soldier_id,resources):
    with pytest.raises(ValueError):insert_missing_manual_jobs(Conn(),soldier_id=soldier_id,resources=resources)