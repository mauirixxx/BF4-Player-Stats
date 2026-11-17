"""Offline cycle selection and single-scope transaction tests."""
from datetime import datetime,timezone,timedelta
from unittest.mock import MagicMock
from bf4ps.general_rank_cycle import select_next_scope,run_once
from bf4ps.general_rank_publisher import METRICS,PLATFORMS

class Row:
    def __init__(self,m,p,t):
        self.metric,self.platform,self.published_at=m,p,t

def fake_conn(rows):
    conn=MagicMock()
    conn.execute.return_value.scalar_one.return_value='0026_general_rank_snapshots'
    conn.execute.return_value.__iter__.return_value=iter(rows)
    return conn

def test_missing_scope_first():
    now=datetime.now(timezone.utc)
    c=fake_conn([Row('kills','all',now)])
    assert select_next_scope(c)==('kills','pc')

def test_oldest_published_first_when_all_scopes_present():
    now=datetime.now(timezone.utc)
    rows=[Row(m,p,now) for m in METRICS for p in PLATFORMS]
    rows[-1].published_at=now-timedelta(days=1)
    assert select_next_scope(fake_conn(rows))==(METRICS[-1],PLATFORMS[-1])

def test_wrong_revision_refused():
    c=fake_conn([])
    c.execute.return_value.scalar_one.return_value='0025_compact_lookup_fk_idx'
    try: select_next_scope(c)
    except RuntimeError: pass
    else: raise AssertionError('Must reject incorrect schema')

def test_dry_run_never_calls_publisher(monkeypatch):
    engine=MagicMock()
    conn=fake_conn([])
    engine.connect.return_value.__enter__.return_value=conn
    def no_publish(*args,**kwargs):
        raise AssertionError('Dry-run published')
    monkeypatch.setattr('bf4ps.general_rank_cycle.build_scope',no_publish)
    assert run_once(engine)=={'scope':('kills','all'),'executed':False}
    engine.begin.assert_not_called()

def test_execute_publishes_once_inside_transaction(monkeypatch):
    engine=MagicMock()
    conn=fake_conn([])
    engine.begin.return_value.__enter__.return_value=conn
    calls=[]
    monkeypatch.setattr('bf4ps.general_rank_cycle.build_scope',
                        lambda c,m,p:(calls.append((c,m,p)) or (101,200)))
    result=run_once(engine,execute=True)
    assert result['generation']==101 and result['population']==200
    assert calls==[(conn,'kills','all')]
    engine.begin.assert_called_once()
