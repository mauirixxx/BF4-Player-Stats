import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'api'
class ExclusionReaderContract(unittest.TestCase):
 def test_public_read_paths_filter_by_platform_and_persona(self):
  for filename in ('general_leaderboard.py','global_soldier_search.py','soldier_detail.py','leaderboard_api.py','community_export.py','temp_dashboard_export.py'):
   with self.subTest(file=filename):
    s=(ROOT/filename).read_text()
    self.assertIn('public.player_exclusions',s)
    self.assertIn('pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active',s)
 def test_aliases_and_aggregate_export_filtered(self):
  s=(ROOT/'leaderboard_api.py').read_text()
  self.assertIn('FROM public.soldier_names n JOIN public.soldiers s',s)
  s=(ROOT/'community_export.py').read_text()
  self.assertIn('WHERE NOT EXISTS',s)
