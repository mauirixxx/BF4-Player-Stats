"""Public equipment artwork override contract."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicArtworkContract(unittest.TestCase):
    def test_override_manifest_loaded_before_initial_catalog(self):
        source = (ROOT / 'site/equipment.html').read_text()
        self.assertIn("fetch('/assets/equipment-overrides/manifest.json'", source)
        self.assertIn('loadArtworkOverrides().then(()=>loadCatalog())', source)

    def test_original_artwork_fallback(self):
        source = (ROOT / 'site/equipment.html').read_text()
        self.assertIn("artworkOverrides[key]?.[role]||equipmentArtwork[key]?.[role]||null", source)

    def test_admin_artwork_controls_present(self):
        source = (ROOT / 'admin/console.html').read_text()
        for name in ('Fancy', 'Hud'):
            for action in ('File', 'Publish', 'Restore', 'History'):
                self.assertIn('id="artwork'+name+action+'"', source)


if __name__ == '__main__':
    unittest.main()
