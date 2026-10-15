import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'api'))
from global_soldier_search import search_soldiers,SEARCH_SQL

class FakeResult:
 def mappings(self):return [{'soldier_id':1,'current_name':'FooeY','detailed_state':'never_attempted'}]
class FakeConnection:
 def execute(self,query,params):
  self.query=str(query);self.params=params
  return FakeResult()
class GlobalSearchTests(unittest.TestCase):
 def test_search_all_identities_with_bounded_results(self):
  c=FakeConnection();r=search_soldiers(c,'  fooey  ')
  self.assertEqual(r['rows'][0]['detailed_state'],'never_attempted')
  self.assertEqual(c.params['pattern'],'%fooey%')
  self.assertIn('soldier_names',c.query)
  self.assertIn('LIMIT 100',c.query)
 def test_wildcards_escaped(self):
  c=FakeConnection();search_soldiers(c,'a_b%')
  self.assertEqual(c.params['pattern'],r'%a\_b\%%')
 def test_empty_search_rejected(self):
  with self.assertRaises(ValueError):search_soldiers(FakeConnection(),'x')
