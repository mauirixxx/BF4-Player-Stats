from types import SimpleNamespace
import pytest
from bf4ps.manual_job_priority import promote_existing_pending_jobs

class FakeConn:
    def __init__(self):
        self.sql = ''
        self.params = None
    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ['weapons', 'profile']))


def test_promotion_is_lease_safe_and_retry_safe():
    c = FakeConn()
    result = promote_existing_pending_jobs(c, soldier_id=42, resources=('profile', 'weapons'))
    assert result == ('weapons', 'profile')
    assert "status = 'pending'" in c.sql
    assert 'last_error_at IS NULL' in c.sql
    assert 'eligible_at <= now()' in c.sql
    assert "lane = 'background'" in c.sql
    assert "priority_class = 'interactive'" in c.sql
    assert 'lease_token' not in c.sql
    assert c.params['soldier_id'] == 42


def test_empty_selection_is_noop():
    c = FakeConn()
    assert promote_existing_pending_jobs(c, soldier_id=1, resources=()) == ()
    assert c.sql == ''

@pytest.mark.parametrize('soldier_id,resources', [(0,('weapons',)),(True,('weapons',)),(1,('invalid',)),(1,('weapons','weapons'))])
def test_invalid_selection_rejected(soldier_id,resources):
    with pytest.raises(ValueError):
        promote_existing_pending_jobs(FakeConn(), soldier_id=soldier_id, resources=resources)