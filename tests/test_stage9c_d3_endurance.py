"""Fail-closed D3 harness unit tests; no database or network access."""
from unittest.mock import Mock
import pytest
from scripts.stage9c_d3_endurance import checked_url, validate_identity, cohorts, reset

URL='postgresql+psycopg://user:secret@localhost/bf4ps_scratch_stage9c_d3'

def test_database_url_guard():
    assert checked_url({'BF4PS_DATABASE_URL':URL,'BF4PS_STAGE9C_D3_URL':URL})==URL
    for env in ({}, {'BF4PS_DATABASE_URL':URL},
                {'BF4PS_DATABASE_URL':URL,'BF4PS_STAGE9C_D3_URL':URL.replace('_d3','_d2')},
                {'BF4PS_DATABASE_URL':URL.replace('_d3','_d2'),'BF4PS_STAGE9C_D3_URL':URL.replace('_d3','_d2')}):
        with pytest.raises(RuntimeError):checked_url(env)

def test_sql_identity_guard():
    c=Mock()
    c.execute.return_value.one.return_value=('bf4ps_scratch_stage9c_d3','bf4ps_stage9c_d2',False,'off')
    c.execute.return_value.scalar_one.return_value='0006_stage9c_soak_round_ledger'
    validate_identity(c)
    for wrong in (('bf4ps_scratch_stage9c_d2','bf4ps_stage9c_d2',False,'off'),
                  ('bf4ps_scratch_stage9c_d3','postgres',False,'off'),
                  ('bf4ps_scratch_stage9c_d3','bf4ps_stage9c_d2',True,'off'),
                  ('bf4ps_scratch_stage9c_d3','bf4ps_stage9c_d2',False,'on')):
        c.execute.return_value.one.return_value=wrong
        with pytest.raises(RuntimeError):validate_identity(c)

def test_cohort_exactness():
    c=Mock()
    c.execute.return_value.all.return_value=[(i+1,f'D3_SYNTH_{site}_{j:03}')
        for i,(site,j) in enumerate((site,j) for site in ('tcou','kah-01','hnl-01') for j in range(1,301))]
    assert {k:len(v) for k,v in cohorts(c).items()}=={'tcou':300,'kah-01':300,'hnl-01':300}
    c.execute.return_value.all.return_value[0]=(1,'OTHER_001')
    with pytest.raises(RuntimeError):cohorts(c)

def test_reset_dry_run_no_writes(monkeypatch):
    monkeypatch.setattr('scripts.stage9c_d3_endurance.preflight',lambda c:{'statuses':{'claimed':900},'collectors':[]})
    c=Mock()
    assert reset(c,execute=False,evidence_path=None)['dry_run']
    c.execute.assert_not_called()

def test_reset_requires_evidence(monkeypatch):
    monkeypatch.setattr('scripts.stage9c_d3_endurance.preflight',lambda c:{'statuses':{'claimed':900},'collectors':[]})
    c=Mock()
    with pytest.raises(RuntimeError,match='evidence'):reset(c,execute=True,evidence_path=None)
    c.execute.assert_not_called()


def test_reset_rejects_snapshot_changed_under_lock(monkeypatch, tmp_path):
    import json
    import scripts.stage9c_d3_endurance as d3
    report = {'database': d3.DB, 'jobs': [{'job_id': 1}], 'collectors': []}
    saved = tmp_path / 'snapshot.json'
    saved.write_text(json.dumps(report))
    monkeypatch.setattr(d3, 'preflight', Mock(side_effect=[report, {**report, 'jobs': [{'job_id': 2}]}]))
    conn = Mock()
    conn.execute.return_value.scalar_one.side_effect = [True, 0]
    conn.execute.return_value.scalars.return_value.all.return_value = list(range(900))
    with pytest.raises(RuntimeError, match='changed under lock'):
        d3.reset(conn, execute=True, evidence_path=str(saved))
    assert not any('UPDATE collection_jobs' in str(call) for call in conn.execute.call_args_list)


def test_reset_rejects_active_advisory_lock(monkeypatch, tmp_path):
    import json
    import scripts.stage9c_d3_endurance as d3
    report = {'database': d3.DB, 'jobs': [], 'collectors': []}
    saved = tmp_path / 'snapshot.json'
    saved.write_text(json.dumps(report))
    monkeypatch.setattr(d3, 'preflight', lambda conn: report)
    conn = Mock()
    conn.execute.return_value.scalar_one.return_value = False
    with pytest.raises(RuntimeError, match='worker active'):
        d3.reset(conn, execute=True, evidence_path=str(saved))
    assert conn.execute.call_count == 1

def test_worker_rejects_wrong_physical_host(monkeypatch):
    import scripts.stage9c_d3_endurance as d3
    monkeypatch.setattr(d3.socket, 'gethostname', lambda: 'not-kah-01')
    engine = Mock()
    with pytest.raises(RuntimeError, match='physical hostname'):
        d3.worker(engine, site='kah-01', seconds=1, max_cycles=1, run_id='test')
    engine.connect.assert_not_called()


def test_worker_registration_failure_releases_advisory_lock(monkeypatch):
    import scripts.stage9c_d3_endurance as d3
    from contextlib import contextmanager
    monkeypatch.setattr(d3.socket, 'gethostname', lambda: 'tcou')
    monkeypatch.setattr(d3, 'preflight', lambda conn: {})
    monkeypatch.setattr(d3, 'cohorts', lambda conn: {'tcou': list(range(300))})
    engine = Mock()
    guard = Mock()
    guard.execute.return_value.scalar_one.return_value = True
    @contextmanager
    def preflight_connection():
        yield Mock()
    @contextmanager
    def registration():
        raise RuntimeError('collector insert rejected')
        yield
    engine.connect.side_effect = [preflight_connection(), guard]
    engine.begin.side_effect = registration
    with pytest.raises(RuntimeError, match='collector insert rejected'):
        d3.worker(engine, site='tcou', seconds=1, max_cycles=1, run_id='test')
    guard.close.assert_called_once()
    assert any('pg_advisory_unlock_shared' in str(call.args[0])
               for call in guard.execute.call_args_list)

