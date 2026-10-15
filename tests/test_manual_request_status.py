from types import SimpleNamespace
import pytest
from bf4ps.manual_request_status import get_manual_request_status

class Conn:
    def __init__(self,row):self.row=row
    def execute(self,sql,params):
        assert 'WHERE r.request_id = :request_id' in str(sql)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda:self.row))

@pytest.mark.parametrize('pending,running,retrying,expected',[
    (4,0,0,'queued'),(3,1,0,'collecting'),(2,0,1,'retrying'),(0,0,0,'accepted'),
])
def test_status_does_not_invent_completion(pending,running,retrying,expected):
    row={'request_id':9,'status':'accepted','pending':pending,'running':running,'retrying':retrying}
    assert get_manual_request_status(Conn(row),9).state==expected

def test_unknown_request():
    assert get_manual_request_status(Conn(None),99) is None

@pytest.mark.parametrize('value',[0,-1,True,'12'])
def test_bad_request_id(value):
    with pytest.raises(ValueError):get_manual_request_status(Conn(None),value)