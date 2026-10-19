import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class SoldierDetailContract(unittest.TestCase):
    def test_staging_fetches_only_one_soldier(self):
        source=(ROOT/'site/soldier-paginated-staging.html').read_text()
        self.assertIn('/bf4ps-api/soldier-detail?id=',source)
        self.assertNotIn('temp-stats-data.json',source)
        self.assertIn('detail.weapons',source)
        self.assertIn('detail.vehicles',source)

    def test_production_soldier_uses_bounded_detail_endpoint(self):
        source=(ROOT/'site/soldier.html').read_text()
        self.assertIn('/bf4ps-api/soldier-detail?id=',source)
        self.assertNotIn('/temp-stats-data.json',source)

    def test_detail_queries_bounded(self):
        source=(ROOT/'api/soldier_detail.py').read_text()
        self.assertEqual(source.count('LIMIT 15'),2)
        self.assertIn('WHERE w.soldier_id=:soldier_id',source)
        self.assertIn('WHERE v.soldier_id=:soldier_id',source)

if __name__=='__main__':unittest.main()
