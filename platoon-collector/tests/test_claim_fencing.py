"""Non-destructive checks for claim fencing and import transaction order."""
import ast
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class ClaimFencingTests(unittest.TestCase):
    def test_all_worker_scripts_parse(self):
        for name in ("platoon_queue_worker.py", "discover_soldier_platoons.py", "import_platoon_rosters.py"):
            with self.subTest(name=name):
                ast.parse((SCRIPTS / name).read_text())

    def test_import_claim_is_locked_before_roster_writes(self):
        src = (SCRIPTS / "import_platoon_rosters.py").read_text()
        self.assertIn("FOR UPDATE", src)
        self.assertIn("RAISE EXCEPTION 'stale platoon claim'", src)
        self.assertLess(src.index('statements.append("DO $$'), src.index("statements.extend(sql_for(doc))"))
        self.assertIn("last_attempt_at={stamp}", src)
        self.assertIn("next_refresh_at={stamp}", src)

    def test_claim_token_propagates_to_import(self):
        src = (SCRIPTS / "platoon_queue_worker.py").read_text()
        self.assertIn("'--claim-token',claim_token", src)
        self.assertIn("platoon_work_leases", src)
        self.assertIn("ON CONFLICT(platoon_id) DO UPDATE", src)

    def test_discovery_completion_and_failure_fenced(self):
        src = (SCRIPTS / "discover_soldier_platoons.py").read_text()
        self.assertEqual(src.count("WHERE soldier_id={int(soldier)} AND {fence}"), 2)

    def test_refresh_request_exclusion_exists(self):
        src = (SCRIPTS / "platoon_queue_worker.py").read_text()
        self.assertIn("NOT EXISTS (SELECT 1 FROM platoon_requests r", src)
        self.assertIn("FOR UPDATE OF p SKIP LOCKED", src)


if __name__ == "__main__":
    unittest.main()
