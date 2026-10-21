"""Regression coverage for compact homepage snapshot."""
import os
import unittest
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

class HomepageSummaryTests(unittest.TestCase):
    def test_summary_counts_match_legacy_browser_semantics(self):
        os.environ.setdefault('BF4PS_DATABASE_URL', 'sqlite://')
        path = Path(__file__).resolve().parents[1] / 'api' / 'temp_dashboard_export.py'
        spec = spec_from_file_location('temp_dashboard_export', path)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        payload = {'updated':'2026-10-15T00:00:00Z', 'summary':{'soldiers':209818,'weapons':4268715,'vehicles':2029254},
                   'soldiers':[{'detailed_state':'success','weapons_state':'success','vehicles_state':'success','profile_state':'success'},
                               {'detailed_state':'success','weapons_state':'pending','vehicles_state':'success','profile_state':'success'},
                               {'detailed_state':'pending','weapons_state':'success','vehicles_state':'success','profile_state':'success'}]}
        result = mod.homepage_summary(payload)
        self.assertEqual(result['detailed_soldiers'],2)
        self.assertEqual(result['full_soldiers'],1)
        self.assertEqual(result['summary']['soldiers'],209818)
        self.assertNotIn('soldiers',result)
        self.assertNotIn('weapons',result)
