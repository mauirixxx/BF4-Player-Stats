"""Compact reader parity checks without a production DB connection."""
import importlib.util
import sys
import types
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1] / 'api'
sys.path.insert(0, str(ROOT))
from bf4ps.compact_rank_codec import encode_block

spec = importlib.util.spec_from_file_location('rank_read_path_compact', ROOT / 'rank_read_path_compact.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class Result:
    def __init__(self, rows):
        self.rows = rows
    def mappings(self):
        return self
    def first(self):
        return self.rows[0] if self.rows else None
    def scalars(self):
        return self
    def all(self):
        return self.rows
    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, excluded=False, published=True):
        self.excluded = excluded
        self.published = published
        self.blocks = [
            {'block_id':0,'first_position':1,'last_position':3,
             'payload':encode_block([(1,1,100,'1.234567890123456789',None,None),
                                     (2,1,100,'2.0',None,None),
                                     (3,3,50,None,'25.25',None)])}]
        self.block_queries = []
        self.people = {1:('Alpha',101,'pc'),2:('Bravo',102,'pc'),3:('Charlie',103,'pc')}
    def execute(self, statement, params=None):
        sql = str(statement)
        if 'FROM equipment_rank_compact_published' in sql:
            return Result([{'generation_id':5,'row_count':3,'completed_at':'test'}] if self.published else [])
        if 'JOIN player_exclusions' in sql:
            return Result([(1,)] if self.excluded else [])
        if 'FROM equipment_rank_compact_lookup l' in sql:
            needle = params['pattern'].strip('%').lower()
            return Result([sid for sid,(name,persona,_) in self.people.items()
                           if needle in name.lower() or needle in str(persona)])
        if 'FROM equipment_rank_compact_blocks' in sql:
            self.block_queries.append(params)
            if params and 'first' in params:
                return Result([b for b in self.blocks if b['last_position'] >= params['first'] and b['first_position'] <= params['last']])
            return Result(self.blocks)
        if 'FROM soldiers WHERE soldier_id' in sql:
            return Result([{'soldier_id':sid,'current_name':self.people[sid][0],
                            'persona_id':self.people[sid][1],'platform':self.people[sid][2]}
                           for sid in params['ids']])
        raise AssertionError(sql)


def get(conn, page=1, page_size=2, search='', division=0):
    return reader.get_compact_page(conn,'weapon','pc',172,page,page_size,search,division,'kills')


def test_pagination_and_ties():
    c = FakeConnection()
    first = get(c)
    second = get(c,page=2)
    assert [r['soldier_id'] for r in first['rows']] == [1,2]
    assert [r['rank'] for r in first['rows']] == [1,1]
    assert [r['soldier_id'] for r in second['rows']] == [3]
    assert second['rows'][0]['position'] == 3
    assert first['filtered_count'] == 3
    assert str(first['rows'][0]['kpm']) == '1.234567890123456789'


def test_name_and_persona_search():
    assert [r['soldier_id'] for r in get(FakeConnection(),search='bra')['rows']] == [2]
    assert [r['soldier_id'] for r in get(FakeConnection(),search='103')['rows']] == [3]
    assert get(FakeConnection(),search='absent')['filtered_count'] == 0


def test_exclusion_and_missing_pointer_fallback():
    assert get(FakeConnection(excluded=True)) is None
    assert get(FakeConnection(published=False)) is None


def test_division_filter():
    assert get(FakeConnection(),division=10)['filtered_count'] == 1
    assert get(FakeConnection(),division=1)['filtered_count'] == 0


def test_ordinary_page_uses_bounded_blocks():
    c = FakeConnection()
    assert [r['soldier_id'] for r in get(c, page=2, page_size=2)['rows']] == [3]
    assert c.block_queries == [{'g':5,'first':3,'last':4}]
    assert get(c, page=3, page_size=2)['rows'] == []
    assert get(c, page=3, page_size=2)['filtered_count'] == 3


def test_filtered_page_keeps_full_scan():
    c = FakeConnection()
    get(c, division=10)
    assert c.block_queries == [{'g':5}]
