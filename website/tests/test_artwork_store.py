"""Unit tests for isolated equipment artwork storage."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from artwork_store import ArtworkStore, transcode_image, validate_identity, allowed_keys


def sample_image():
    image = Image.new('RGBA', (48, 20), (50, 120, 180, 255))
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


class ArtworkTests(unittest.TestCase):
    def test_image_transcode(self):
        data, dims = transcode_image(sample_image())
        self.assertEqual(dims, (48, 20))
        self.assertEqual(Image.open(io.BytesIO(data)).format, 'WEBP')

    def test_reject_invalid_images(self):
        for data in (b'', b'<svg></svg>', b'not-an-image', b'x' * (4 * 1024 * 1024 + 1)):
            with self.subTest(data=data[:10]), self.assertRaises(ValueError):
                transcode_image(data)

    def test_identity(self):
        self.assertEqual(validate_identity('weapon', 'WARSAW_ID_P_WNAME_M416', 'hud'),
                         'weapon-WARSAW_ID_P_WNAME_M416')
        for key in ('../oops', 'WARSAW_ID_../evil', ''):
            with self.assertRaises(ValueError):
                validate_identity('weapon', key, 'fancy')

    def test_publish_restore_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity = 'weapon-WARSAW_ID_P_WNAME_M416'
            (Path(tmp) / 'public').mkdir()
            store = ArtworkStore(Path(tmp) / 'private', Path(tmp) / 'public', {identity}, Path(__file__).resolve().parents[1] / 'site' / 'equipment-artwork.js')
            fancy = store.publish('weapon', 'WARSAW_ID_P_WNAME_M416', 'fancy', sample_image(), 'mauirixxx')
            hud = store.publish('weapon', 'WARSAW_ID_P_WNAME_M416', 'hud', sample_image(), 'mauirixxx')
            self.assertNotEqual(fancy['url'], hud['url'])
            self.assertEqual(len(store.history('weapon', 'WARSAW_ID_P_WNAME_M416', 'fancy')), 1)
            self.assertEqual(len(store.manifest()[identity]), 2)
            self.assertEqual(store.restore('weapon', 'WARSAW_ID_P_WNAME_M416', 'fancy', 'mauirixxx'),
                             {'changed': True})
            self.assertNotIn('fancy', store.manifest()[identity])
            self.assertIn('hud', store.manifest()[identity])
            self.assertEqual(len(store.history('weapon', 'WARSAW_ID_P_WNAME_M416', 'fancy')), 2)
            self.assertEqual(store.restore('weapon', 'WARSAW_ID_P_WNAME_M416', 'fancy', 'mauirixxx'),
                             {'changed': False})

    def test_unknown_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtworkStore(Path(tmp) / 'p', Path(tmp) / 'w', set())
            with self.assertRaises(ValueError):
                store.publish('weapon', 'WARSAW_ID_P_WNAME_M416', 'fancy', sample_image(), 'mauirixxx')

    def test_existing_catalog(self):
        path = Path(__file__).resolve().parents[1] / 'site' / 'equipment-artwork.js'
        catalog = allowed_keys(path)
        self.assertIn('weapon-WARSAW_ID_P_WNAME_M416', catalog)
        self.assertIn('vehicle-WARSAW_ID_P_VNAME_AH1Z', catalog)


if __name__ == '__main__':
    unittest.main()
