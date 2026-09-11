import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as editor_app


class PreviewCacheTests(unittest.TestCase):
    def setUp(self):
        with editor_app.preview_cache_lock:
            editor_app.preview_cache.clear()

    def test_preview_source_is_cached_and_copied(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.jpg"
            Image.new("RGB", (1200, 800), (90, 130, 170)).save(path, quality=95)
            first, first_hit = editor_app._preview_source(str(path))
            second, second_hit = editor_app._preview_source(str(path))
            self.assertFalse(first_hit)
            self.assertTrue(second_hit)
            self.assertEqual(first.size, second.size)
            self.assertIsNot(first, second)

    def test_cache_invalidates_when_source_changes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.jpg"
            Image.new("RGB", (800, 600), "red").save(path, quality=90)
            editor_app._preview_source(str(path))
            Image.new("RGB", (900, 600), "blue").save(path, quality=91)
            changed, hit = editor_app._preview_source(str(path))
            self.assertFalse(hit)
            self.assertEqual(changed.size, (900, 600))

    def test_linear_preview_is_rgba16f_with_precision_headers(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.png"
            Image.new("RGB", (32, 24), (90, 130, 170)).save(path)
            response = editor_app.linear_preview(str(path))
            self.assertEqual(response.media_type, "application/octet-stream")
            self.assertEqual(response.headers["x-pixel-format"], "RGBA16F-linear")
            self.assertEqual(response.headers["x-width"], "32")
            self.assertEqual(response.headers["x-height"], "24")
            self.assertEqual(len(response.body), 32 * 24 * 4 * 2)

    def test_resident_upload_keeps_resolution_above_preview_master(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'resident.png'
            Image.new('RGB', (2800, 40), (90, 130, 170)).save(path)
            response = editor_app.linear_preview(str(path), resident=True, max_side=4096)
            self.assertEqual(response.headers['x-width'], '2800')
            self.assertEqual(len(response.body), 2800 * 40 * 8)
            self.assertFalse(editor_app.preview_cache)

    def test_resident_upload_respects_device_limit(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'resident.png'
            Image.new('RGB', (2800, 40), 'white').save(path)
            response = editor_app.linear_preview(str(path), resident=True, max_side=1800)
            self.assertEqual(response.headers['x-width'], '1800')


if __name__ == "__main__":
    unittest.main()
