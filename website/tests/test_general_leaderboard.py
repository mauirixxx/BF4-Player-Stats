"""Pure query-contract tests; no production database required."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'api'))
from general_leaderboard import query_page

class FakeResult:
    def __init__(self,rows):self.rows=rows
    def mappings(self):return self
    def one(self):return self.rows[0]
    def __iter__(self):return iter(self.rows)
    def scalar_one(self):return self.rows[0]
class FakeConnection:
    def __init__(self):self.calls=[]
    def execute(self,sql,params):
        self.calls.append((str(sql),params.copy()))
        if 'filtered_count' in str(sql):return FakeResult([{'filtered_count':51,'population':1000}])
        return FakeResult([{'soldier_id':51,'rank':51,'value':500}])
class GeneralLeaderboardTests(unittest.TestCase):
    def test_page_bounded_with_global_ranking_and_alias_search(self):
        c=FakeConnection();r=query_page(c,'kills','pc',page=2,page_size=50,search='cherch1',division=2)
        self.assertEqual(r['population'],1000)
        self.assertEqual(r['total_pages'],2)
        self.assertEqual(r['rows'][0]['rank'],51)
        self.assertEqual(c.calls[0][1]['offset'],50)
        self.assertEqual(c.calls[0][1]['pattern'],'%cherch1%')
        self.assertIn('rank() OVER (ORDER BY value DESC)',c.calls[1][0])
        self.assertIn('row_number() OVER (ORDER BY value DESC,soldier_id)',c.calls[1][0])
        self.assertIn('EXISTS (SELECT 1 FROM soldier_names',c.calls[1][0])
        self.assertIn('LIMIT :limit OFFSET :offset',c.calls[1][0])
    def test_rejects_untrusted_column_names(self):
        with self.assertRaises(ValueError):query_page(FakeConnection(),'kills; DROP TABLE soldiers','all')
        with self.assertRaises(ValueError):query_page(FakeConnection(),'kills','all',page_size=10000)
        with self.assertRaises(ValueError):query_page(FakeConnection(),'kills','ps3')
