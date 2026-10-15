from types import SimpleNamespace
from unittest.mock import patch
import pytest
from bf4ps.manual_request_service import submit_existing_soldier_url

URL='https://battlelog.battlefield.com/bf4/soldier/mauirixxx/stats/236753552/pc/'

class Conn:
    def __init__(self, soldier_id=42):self.soldier_id=soldier_id;self.params=None
    def execute(self,sql,params):
        self.params=params
        return SimpleNamespace(scalar_one_or_none=lambda:self.soldier_id)

class Engine:
    def __init__(self,conn):self.conn=conn;self.entered=False
    def begin(self):
        engine=self
        class Context:
            def __enter__(self):engine.entered=True;return engine.conn
            def __exit__(self,*args):engine.entered=False
        return Context()


def test_authoritative_persona_platform_lookup():
    c=Conn();e=Engine(c)
    result=SimpleNamespace(accepted=True,request_id=12,created=('profile',),promoted=('weapons',))
    with patch('bf4ps.manual_request_service.admit_registered_soldier',return_value=result) as admit:
        response=submit_existing_soldier_url(e,URL)
    assert c.params=={'platform':'pc','persona_id':236753552}
    admit.assert_called_once_with(c,soldier_id=42,kind='refresh')
    assert response.state=='accepted' and response.jobs_created==1 and response.jobs_promoted==1


def test_unknown_identity_does_not_enqueue():
    with patch('bf4ps.manual_request_service.admit_registered_soldier') as admit:
        assert submit_existing_soldier_url(Engine(Conn(None)),URL).state=='not_registered'
    admit.assert_not_called()


def test_bad_url_never_opens_transaction():
    e=Engine(Conn())
    with pytest.raises(ValueError):submit_existing_soldier_url(e,'http://evil.invalid/')
    assert not e.entered


def test_invalid_kind_never_opens_transaction():
    e=Engine(Conn())
    with pytest.raises(ValueError):submit_existing_soldier_url(e,URL,kind='urgent')
    assert not e.entered


def test_cooldown_response():
    result=SimpleNamespace(accepted=False,request_id=9,retry_after_seconds=3590)
    with patch('bf4ps.manual_request_service.admit_registered_soldier',return_value=result):
        response=submit_existing_soldier_url(Engine(Conn()),URL)
    assert response.state=='cooldown' and response.retry_after_seconds==3590