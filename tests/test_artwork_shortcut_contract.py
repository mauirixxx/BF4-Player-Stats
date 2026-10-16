"""Admin-only shortcut and editor routing contract."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ShortcutContract(unittest.TestCase):
    def test_admin_button_is_hidden_by_default_and_session_checked(self):
        page=(ROOT/'site/equipment.html').read_text()
        self.assertIn('.admin-edit{display:none;',page)
        self.assertIn("fetch('/bf4ps-admin-api/session'",page)
        self.assertIn("adminArtworkSession&&item",page)

    def test_editor_uses_identity_and_returns_to_selected_equipment(self):
        script=(ROOT/'admin/artwork-editor.js').read_text()
        self.assertIn("new URLSearchParams(location.search)",script)
        self.assertIn("back.searchParams.set('item',item)",script)
        self.assertIn("location.assign(back.pathname+back.search)",script)

    def test_editor_uses_authenticated_api_and_independent_roles(self):
        script=(ROOT/'admin/artwork-editor.js').read_text()
        self.assertIn("'X-CSRF-Token':csrf",script)
        self.assertIn("['fancy','hud']",script)
        self.assertIn("artwork/publish?",script)
        self.assertIn("artwork/restore",script)

if __name__=='__main__':
    unittest.main()
