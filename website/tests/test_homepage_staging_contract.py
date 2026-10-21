import unittest
from pathlib import Path

class StagingHomepageContract(unittest.TestCase):
 def test_staging_never_downloads_bulk_snapshot(self):
  html=(Path(__file__).resolve().parents[1]/'site'/'index-paginated-staging.html').read_text()
  self.assertNotIn('temp-stats-data.json',html)
  self.assertIn('homepage-paginated.js',html)
  self.assertIn('BF4PSPaginated.summary()',html)
  self.assertIn('BF4PSPaginated.general(',html)
  self.assertIn('BF4PSPaginated.search(',html)
 def test_soldier_deep_link_uses_server_rank(self):
  html=(Path(__file__).resolve().parents[1]/'site'/'index-paginated-staging.html').read_text()
  self.assertIn('pendingJump&&highlightedPersona',html)
  self.assertIn('Math.floor((Number(hit.position)-1)/50)',html)
