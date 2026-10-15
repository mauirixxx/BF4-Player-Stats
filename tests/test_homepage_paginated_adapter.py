import unittest
from pathlib import Path

class PaginatedAdapterTests(unittest.TestCase):
    def test_adapter_uses_only_small_endpoints(self):
        js=(Path(__file__).resolve().parents[1]/'site'/'homepage-paginated.js').read_text()
        self.assertIn('/homepage-summary.json',js)
        self.assertIn('/bf4ps-api/general-leaderboard',js)
        self.assertIn('/bf4ps-api/global-soldier-search',js)
        self.assertNotIn('temp-stats-data.json',js)
        self.assertIn('AbortSignal.timeout',js)
