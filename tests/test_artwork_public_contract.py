"""Public equipment artwork override contract."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicArtworkContract(unittest.TestCase):
    def test_canonical_artwork_paths(self):
        source = (ROOT / 'site/equipment.html').read_text()
        self.assertNotIn('equipment-overrides', source)
        self.assertIn('loadCatalog()', source)

    def test_original_artwork_fallback(self):
        source = (ROOT / 'site/equipment.html').read_text()
        self.assertIn("equipmentArtwork[kind+'-'+item.name]?.[role]||null", source)

    def test_admin_artwork_controls_present(self):
        source = (ROOT / 'admin/console.html').read_text()
        for name in ('Fancy', 'Hud'):
            for action in ('File', 'Publish', 'Restore', 'History'):
                self.assertIn('id="artwork'+name+action+'"', source)


if __name__ == '__main__':
    unittest.main()
