"""Fast contract checks; database race tests require an isolated PostgreSQL fixture."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "bf4ps" / "distributed_rank_queue.py"
BUILDER = ROOT / "build_rank_hourly.py"
WORKER = ROOT / "distributed_rank_worker.py"
MIGRATION = ROOT / "migrations" / "versions" / "0018_distributed_rank_queue.py"

class DistributedRankContract(unittest.TestCase):
    def test_syntax(self):
        for path in (QUEUE, BUILDER, WORKER, MIGRATION):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(), filename=str(path))

    def test_serialized_capacity(self):
        code = QUEUE.read_text()
        self.assertIn("WHERE id=1 FOR UPDATE", code)
        self.assertIn("FOR UPDATE SKIP LOCKED LIMIT 1", code)
        self.assertIn("lease_expires_at > clock_timestamp()", code)
        self.assertIn("claim_epoch=claim_epoch+1", code)

    def test_fenced_publication(self):
        code = BUILDER.read_text()
        self.assertIn("rank-claim-token", code)
        self.assertIn("claim_epoch=:epoch", code)
        self.assertIn("publication denied", code)
        self.assertIn("FOR UPDATE", code)

    def test_explicit_production_opt_in(self):
        code = WORKER.read_text()
        self.assertIn('BF4PS_DISTRIBUTED_RANK_ENABLE', code)
        self.assertIn('BF4PS_DISTRIBUTED_RANK_REQUIRED', code)
        self.assertIn('process.terminate()', code)

    def test_initial_capacity_one(self):
        code = MIGRATION.read_text()
        self.assertIn("VALUES(1,1,180)", code)
        self.assertIn("max_active_builds >= 0", code)

if __name__ == "__main__":
    unittest.main()
