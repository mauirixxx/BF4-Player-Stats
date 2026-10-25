"""Fast contract tests for the private moderation service (no production mutations)."""
import unittest
from types import SimpleNamespace
from api.admin_moderation_service import validate_identity, set_exclusion


class FakeConnection:
    def __init__(self, previous=None):
        self.previous = previous
        self.statements = []

    def execute(self, sql, params):
        query = str(sql)
        self.statements.append(query)
        if 'SELECT platform,persona_id,reason_code' in query:
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: self.previous))
        return SimpleNamespace()


class ModerationTests(unittest.TestCase):
    def test_invalid_identity(self):
        for platform, persona in [('PC', 123), ('pc', 0), ('pc', True), ('pc', 2**63)]:
            with self.assertRaises(ValueError):
                validate_identity(platform, persona)

    def test_exclude_writes_registry_and_audit(self):
        conn = FakeConnection()
        result = set_exclusion(conn, platform='pc', persona_id=1007062617638,
                               active=True, actor='admin', reason_code='data_integrity_anomaly')
        self.assertEqual(result, {'changed': True, 'active': True})
        self.assertEqual(len(conn.statements), 4)
        self.assertIn('pg_advisory_xact_lock', conn.statements[0])
        self.assertIn('INSERT INTO public.player_exclusion_audit', conn.statements[3])

    def test_same_state_is_idempotent(self):
        conn = FakeConnection({'active': True})
        result = set_exclusion(conn, platform='pc', persona_id=123,
                               active=True, actor='admin', reason_code='operator_review')
        self.assertEqual(result, {'changed': False, 'active': True})
        self.assertEqual(len(conn.statements), 2)

    def test_restore_requires_existing_registry(self):
        with self.assertRaises(ValueError):
            set_exclusion(FakeConnection(), platform='pc', persona_id=123,
                          active=False, actor='admin', reason_code='operator_review')


if __name__ == '__main__':
    unittest.main()
