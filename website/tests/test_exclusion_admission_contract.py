import unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
class ExclusionAdmissionContract(unittest.TestCase):
 def test_database_guards_cover_rediscovery_jobs_and_verification(self):
  sql=(root/'migrations/0013b_exclusion_database_guards.sql').read_text()
  for table in ('public.soldiers','public.collection_jobs','public.manual_soldier_verifications'):
   self.assertIn('ON '+table,sql)
  self.assertIn('AND e.active',sql)
  self.assertIn('BEFORE INSERT',sql)
 def test_manual_api_returns_excluded_without_mutation(self):
  s=(root/'api/manual_request_api.py').read_text()
  self.assertIn("'state': 'excluded'",s)
  self.assertIn("('not_registered', 'excluded')",s)
