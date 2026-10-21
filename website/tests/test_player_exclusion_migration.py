import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class PlayerExclusionMigrationContract(unittest.TestCase):
    def test_identity_and_audit(self):
        sql=(ROOT/'migrations/0013_player_exclusions.sql').read_text()
        self.assertIn('PRIMARY KEY (platform, persona_id)',sql)
        self.assertIn('player_exclusion_audit',sql)
        self.assertIn('active boolean NOT NULL DEFAULT true',sql)
        self.assertNotIn('DELETE FROM soldiers',sql)
        self.assertNotIn('1007062617638',sql)
    def test_design_requires_all_guards_before_activation(self):
        design=(ROOT/'docs/PLAYER-EXCLUSION-AND-ADMIN-MODERATION-DESIGN.md').read_text()
        for phrase in ('before persistence','manual submission','rediscovery','aggregates','audit'):
            self.assertIn(phrase,design.lower())
