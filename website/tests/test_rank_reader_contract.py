"""Guard the opt-in ranking reader contract without a production database."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'api'

class RankReaderContract(unittest.TestCase):
    def test_repeatable_read_and_read_only(self):
        source = (ROOT / 'leaderboard_api.py').read_text()
        self.assertIn("isolation_level='REPEATABLE READ'", source)
        self.assertIn("SET TRANSACTION READ ONLY", source)

    def test_reader_fail_closed_to_fallback(self):
        source = (ROOT / 'leaderboard_api.py').read_text()
        self.assertIn("if precomputed is not None:", source)
        self.assertIn("return precomputed", source)
        self.assertIn("BF4PS_PRECOMPUTED_RANK_READS", source)

    def test_only_one_summary_publisher(self):
        source = (ROOT / 'temp_dashboard_export.py').read_text()
        self.assertNotIn("homepage-summary.json", source)
        dedicated = (ROOT / 'homepage_summary_export.py').read_text()
        self.assertIn("homepage-summary.json", dedicated)

if __name__ == '__main__':
    unittest.main()
