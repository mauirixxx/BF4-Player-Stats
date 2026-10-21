"""Keep homepage metric selector aligned with the paginated API allowlist."""
import re
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'api'))
from general_leaderboard import METRICS

class HomepageMetricCompatibility(unittest.TestCase):
    def test_every_general_homepage_metric_is_supported(self):
        page=(ROOT/'site'/'index.html').read_text()
        select=re.search(r'<select[^>]+id="metric"[^>]*>(.*?)</select>',page,re.S)
        self.assertIsNotNone(select)
        values=set(re.findall(r'<option value="([^"]+)',select.group(1)))
        self.assertEqual(values-{'weapon','vehicle'},METRICS)
