"""Production publication authorization must fail closed before any database access."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

BUILDER = Path(__file__).resolve().parents[1] / 'build_compact_rank.py'
BASE = ['--kind', 'weapon', '--item', '1', '--platform', 'pc',
        '--metric', 'kills', '--snapshot-format', '2', '--publish',
        '--rank-worker-id', '00000000-0000-0000-0000-000000000001',
        '--rank-claim-token', '00000000-0000-0000-0000-000000000002',
        '--rank-claim-epoch', '1']

class ProductionAuthorizationTests(unittest.TestCase):
    def run_builder(self, args=(), scope=None):
        env = dict(os.environ, BF4PS_DATABASE_URL='postgresql://invalid:invalid@127.0.0.1:1/bf4_playerstats')
        env.pop('BF4PS_COMPACT_PRODUCTION_SCOPE', None)
        if scope is not None:
            env['BF4PS_COMPACT_PRODUCTION_SCOPE'] = scope
        return subprocess.run([sys.executable, str(BUILDER), *BASE, *args],
                              env=env, capture_output=True, text=True, timeout=10)

    def test_missing_ack_denied(self):
        r = self.run_builder(scope='weapon:1:pc:kills')
        self.assertIn('production publication requires', r.stderr)

    def test_missing_scope_denied(self):
        r = self.run_builder(('--production-ack',))
        self.assertIn('production publication requires', r.stderr)

    def test_other_scope_denied(self):
        r = self.run_builder(('--production-ack',), scope='weapon:2:pc:kills')
        self.assertIn('production publication requires', r.stderr)

    def test_matching_scope_passes_authorization_and_reaches_database(self):
        r = self.run_builder(('--production-ack',), scope='weapon:1:pc:kills')
        self.assertNotIn('production publication requires', r.stderr)
        self.assertNotEqual(r.returncode, 0)  # intentionally unreachable database

if __name__ == '__main__':
    unittest.main()
