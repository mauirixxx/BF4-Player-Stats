from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from bf4ps.background_service import claim_production_background_job, MANUAL_MAX_SHARE, BackgroundServiceUsage

class Result:
    def __init__(self,value):self.value=value
    def scalar_one(self):return self.value

class Conn:
    def __init__(self,used=0,limit=4800):self.used=used;self.limit=limit
    def execute(self,sql):
        s=str(sql)
        if 'pg_advisory_xact_lock' in s:return Result(None)
        if 'SELECT EXISTS' in s:return Result(False)
        if 'background_slots_per_hour' in s:return Result(self.limit)
        if "metadata->>'priority_class' = 'interactive'" in s:return Result(self.used)
        raise AssertionError(s)


def test_manual_first_when_under_ceiling():
    calls=[]
    def claim(*args,**kwargs):
        calls.append(kwargs['priority_classes'])
        return object()
    with patch('bf4ps.background_service._usage',return_value=BackgroundServiceUsage(0,0,0,0)),patch('bf4ps.background_service.claim_next_job',side_effect=claim):
        assert claim_production_background_job(Conn(),collector_uuid=uuid4(),resource='weapons') is not None
    assert calls==[('interactive',)]


def test_manual_ceiling_prevents_bypass_by_fallback():
    calls=[]
    def claim(*args,**kwargs):
        calls.append(kwargs.get('priority_classes'))
        return None
    with patch('bf4ps.background_service._usage',return_value=BackgroundServiceUsage(0,0,0,0)),patch('bf4ps.background_service.claim_next_job',side_effect=claim):
        assert claim_production_background_job(Conn(used=480),collector_uuid=uuid4(),resource='weapons') is None
    assert ('interactive',) not in calls
    assert all(x is not None and 'interactive' not in x for x in calls)


def test_share_is_a_ceiling_not_reserved_capacity():
    assert MANUAL_MAX_SHARE == 0.10
    source=Path('bf4ps/background_service.py').read_text()
    assert "metadata->>'priority_class' = 'interactive'" in source
    assert 'manual_used < manual_ceiling' in source