"""Offline API contract tests; full SQL parity needs populated 0013 staging."""
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'api'))
from indexed_equipment_top10 import enabled,query_top10

class Result:
    def __init__(self,rows):self.rows=rows
    def scalar_one(self):return self.rows
    def mappings(self):return self
    def __iter__(self):return iter(self.rows)

class Conn:
    def __init__(self,rows,population):self.rows=rows;self.population=population;self.queries=[]
    def execute(self,query,params):
        sql=str(query);self.queries.append((sql,params))
        return Result(self.population if 'equipment_population' in sql else self.rows)

class TestFastPath(unittest.TestCase):
    def test_flag_off_by_default(self):
        previous=os.environ.pop('BF4PS_INDEXED_EQUIPMENT_READS',None)
        try:self.assertFalse(enabled())
        finally:
            if previous is not None:os.environ['BF4PS_INDEXED_EQUIPMENT_READS']=previous
    def test_ties_population_divisions(self):
        rows=[dict(soldier_id=i,kills=k,kpm=None,accuracy=None) for i,k in ((1,100),(2,100),(3,90))]
        c=Conn(rows,100)
        output=query_top10(c,'weapon','pc',5,'kills')
        self.assertEqual([r['rank'] for r in output['rows']],[1,1,3])
        self.assertEqual([r['division'] for r in output['rows']],[1,1,1])
        self.assertEqual(output['population'],100)
        self.assertIn('equipment_population',c.queries[0][0])
        self.assertNotIn('leaderboard_metrics',c.queries[0][0])
        self.assertIn('player_exclusions',c.queries[1][0])
        self.assertIn('LIMIT 10',c.queries[1][0])
        self.assertIn('m.kills DESC NULLS LAST,m.soldier_id',c.queries[1][0])
    def test_vehicle_kpm_and_null_ties(self):
        c=Conn([dict(soldier_id=1,kills=10,kpm=None),dict(soldier_id=2,kills=4,kpm=None)],2)
        result=query_top10(c,'vehicle','all',41,'kpm')
        self.assertEqual([r['rank'] for r in result['rows']],[1,1])
        self.assertEqual([r['accuracy'] for r in result['rows']],[None,None]) if all('accuracy' in r for r in result['rows']) else None
        self.assertIn('vehicle_leaderboard_metrics',c.queries[1][0])
    def test_invalid_metric(self):
        with self.assertRaises(ValueError):query_top10(Conn([],0),'vehicle','all',1,'accuracy')

if __name__=='__main__':unittest.main()
