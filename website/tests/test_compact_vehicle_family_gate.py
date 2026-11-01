import importlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))

def test_family_fallback(monkeypatch):
    monkeypatch.setenv('BF4PS_DATABASE_URL','postgresql+psycopg://unused@127.0.0.1/unused')
    monkeypatch.setenv('BF4PS_COMPACT_RANK_READS','1')
    api=importlib.import_module('leaderboard_api')
    compact=importlib.import_module('rank_read_path_compact')
    def unsafe(*args):
        raise AssertionError('family incorrectly used compact reader')
    monkeypatch.setattr(compact,'get_compact_page',unsafe)
    monkeypatch.setattr(api,'indexed_equipment_top10',lambda *args: {'legacy':True})
    assert api.get_page(object(),'vehicle','pc',2,1,50,'',0,'kills')=={'legacy':True}
