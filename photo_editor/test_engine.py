import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import cv2
from PIL import Image
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import (DEFAULT_RECIPE, PRESETS, LinearImage, clipping_stats,
                    half_float_rgba, jpeg_bytes, load_image, normalize_recipe,
                    process, process_array)


class EngineTests(unittest.TestCase):
    def test_old_version_tags_are_ignored_and_neutral_is_identity(self):
        from engine import _tone
        rgb=np.repeat(np.linspace(0,8,3000,dtype=np.float32)[None,:,None],3,axis=2)
        old=normalize_recipe({'shadows':37,'highlights':-42})
        np.testing.assert_array_equal(_tone(rgb,old),_tone(rgb,{**old,'tone_engine':1}))
        np.testing.assert_array_equal(_tone(rgb,old),_tone(rgb,{**old,'tone_engine':2}))
        np.testing.assert_allclose(_tone(rgb,normalize_recipe({'tone_engine':2})),rgb,atol=2e-6)

    def test_shadows_strong_lift_confined_to_original_range(self):
        from engine import _tone
        rgb=np.repeat(np.array([.000001,.01,.05,.1,.2,.28,.4,.8,1.,2.],np.float32)[None,:,None],3,axis=2)
        for strength in [-100,-50,0,25,50,75,100]:
            out=_tone(rgb,normalize_recipe({'shadows':strength}))
            np.testing.assert_allclose(out[0,5:],rgb[0,5:],atol=1e-7)
            self.assertTrue((np.diff(out[0,:,0])>0).all())
        out=_tone(rgb,normalize_recipe({'shadows':100}))
        self.assertAlmostEqual(float(np.log2(out[0,0,0]/rgb[0,0,0])),5,places=3)
        self.assertGreater(float(out[0,1,0]),.14)
        self.assertGreater(float(out[0,2,0]),.23)
        self.assertLess(float(out[0,3,0]),.28)

    def test_shadow_boundary_has_smooth_join_and_preserves_color(self):
        from engine import _tone
        rgb=np.repeat(np.array([.2799,.28,.2801],np.float32)[None,:,None],3,axis=2)
        for strength in [-100,100]:
            out=_tone(rgb,normalize_recipe({'shadows':strength}))
            slope=np.diff(out[0,:,0])/.0001
            np.testing.assert_allclose(slope,[1,1],atol=.025)
        color=np.array([[[.32,.4,.48]]],np.float32)
        np.testing.assert_allclose(_tone(color,normalize_recipe({'shadows':100})),color,atol=1e-7)

    def test_log_highlights_keep_order_without_old_ceiling(self):
        from engine import _tone
        rgb=np.repeat(np.array([.01,.1,.18,1.,4.,8.,16.],np.float32)[None,:,None],3,axis=2)
        out=_tone(rgb,normalize_recipe({'highlights':-100}))
        np.testing.assert_allclose(out[0,:3],rgb[0,:3],atol=1e-7)
        self.assertTrue((np.diff(out[0,:,0])>0).all())
        self.assertLess(float(out.max()),1)

    def test_recovery_monotonic_and_retains_highlight_detail(self):
        from engine import _tone
        ramp=np.linspace(0,8,20000,dtype=np.float32)
        rgb=np.repeat(ramp[None,:,None],3,axis=2)
        for shadows in [-100,0,100]:
            for highlights in [-100,0,100]:
                out=_tone(rgb,normalize_recipe({'tone_engine':2,'shadows':shadows,'highlights':highlights}))
                self.assertTrue(np.isfinite(out).all())
                self.assertTrue((np.diff(out[0,:,0])>=-1e-6).all())
        out=_tone(rgb,normalize_recipe({'tone_engine':2,'highlights':-100}))
        self.assertLess(float(out.max()),1)
        self.assertGreater(float(out[0,-1,0]),float(out[0,-100,0]))
        self.assertEqual(float(out[0,0,0]),0)

    def test_recovery_lifts_deep_shadows_and_preserves_channel_ratios(self):
        from engine import _tone
        rgb=np.array([[[.001,.002,.003]]],dtype=np.float32)
        out=_tone(rgb,normalize_recipe({'tone_engine':2,'shadows':100}))
        self.assertGreater(float(out[0,0,0]),.01)
        np.testing.assert_allclose(out[0,0]/out[0,0,0],[1,2,3],rtol=1e-5)

    def test_brush_feather_erase_and_resolution(self):
        from engine import _mask
        stroke = {"size": .4, "feather": 50, "flow": 100, "opacity": 100, "points": [[.5, .5]]}
        spec = {"type": "brush", "strokes": [stroke]}
        mask = _mask((100, 200), spec)
        self.assertEqual(mask[50, 100], 1)
        self.assertEqual(mask[0, 0], 0)
        self.assertTrue(0 < mask[50, 115] < 1)
        large = _mask((200, 400), spec)
        self.assertAlmostEqual(float(mask.mean()), float(large.mean()), places=3)
        erased = _mask((100, 200), {"type":"brush", "strokes":[stroke, {**stroke,"erase":True}]})
        self.assertEqual(erased[50, 100], 0)
        partial = _mask((100, 200), {"type":"brush", "strokes":[{**stroke,"opacity":50}]})
        self.assertAlmostEqual(float(partial[50, 100]), .5)
        capped = _mask((100, 200), {"type":"brush", "strokes":[{**stroke,"opacity":50,"points":[[.5,.5]]*10}]})
        self.assertAlmostEqual(float(capped[50, 100]), .5)

    def test_brush_adjustment_preserves_source_and_exports(self):
        from engine import develop_linear
        import json
        pixels = np.full((100, 200, 3), .2, np.float32)
        spec = {"type":"brush", "exposure":1, "strokes":[{"size":.4,"feather":50,"flow":100,"opacity":100,"points":[[.5,.5]]}]}
        recipe = json.loads(json.dumps({"masks":[spec],"sharpen":0,"denoise":0}))
        developed, _ = develop_linear(LinearImage(pixels), recipe)
        self.assertAlmostEqual(float(developed[50,100,0]), .4, places=5)
        self.assertAlmostEqual(float(developed[0,0,0]), .2, places=5)
        self.assertTrue(np.all(pixels == np.float32(.2)))
        self.assertGreater(len(jpeg_bytes(process(LinearImage(pixels), recipe))), 100)

    def test_mask_visibility_amount_and_neutral_new_mask(self):
        from engine import develop_linear
        source = LinearImage(np.full((60, 80, 3), .2, np.float32))
        mask = {"type":"brush", "exposure":1, "strokes":[{"size":.5,"feather":0,"flow":100,"opacity":100,"points":[[.5,.5]]}]}
        hidden, _ = develop_linear(source, {"masks":[{**mask,"enabled":False}]})
        neutral, _ = develop_linear(source, {"masks":[{**mask,"exposure":0}]})
        half, _ = develop_linear(source, {"masks":[{**mask,"amount":50}]})
        np.testing.assert_allclose(hidden, source.pixels, atol=1e-7)
        np.testing.assert_allclose(neutral, source.pixels, atol=1e-7)
        self.assertAlmostEqual(float(half[30,40,0]), .2 * 2**.5, places=5)

    def setUp(self):
        x = np.linspace(0, 255, 320, dtype=np.uint8)
        rgb = np.dstack([np.tile(x, (240, 1)), np.tile(x[::-1], (240, 1)), np.full((240, 320), 110, np.uint8)])
        self.image = Image.fromarray(rgb, "RGB")

    def test_all_reference_presets_render(self):
        for name in PRESETS:
            recipe = normalize_recipe({"preset": name})
            out = process(self.image, recipe, preview=True)
            self.assertEqual(out.size, self.image.size)
            self.assertGreater(len(jpeg_bytes(out)), 1000)

    def test_crop_and_local_mask(self):
        recipe = dict(DEFAULT_RECIPE)
        recipe.update({"crop": [.25, .25, .5, .5], "masks": [{"type": "ellipse", "x": .5, "y": .5, "width": .3, "height": .3, "feather": 60, "exposure": 1.0}]})
        out = process(self.image, recipe)
        self.assertEqual(out.size, (160, 120))

    def test_export_writes_jpeg(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.jpg"
            path.write_bytes(jpeg_bytes(process(self.image, DEFAULT_RECIPE)))
            with Image.open(path) as saved:
                self.assertEqual(saved.format, "JPEG")

    def test_16_bit_tiff_keeps_more_than_8_bit_precision(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "precision.tiff"
            ramp = np.arange(4096, dtype=np.uint16).reshape(64, 64) * 16
            rgb = np.dstack((ramp, ramp + 1, ramp + 2))
            self.assertTrue(cv2.imwrite(str(path), rgb))
            loaded = load_image(path)
            self.assertEqual(loaded.source_bits, 16)
            self.assertEqual(loaded.pixels.dtype, np.float32)
            self.assertGreater(np.unique(loaded.pixels[..., 0]).size, 256)

    def test_processing_stays_float_until_final_jpeg(self):
        pixels = np.array([[[.25, .5, .75], [.25001, .50001, .75001]]], np.float32)
        source = LinearImage(pixels, 16, "test linear")
        rendered = process_array(source, {**DEFAULT_RECIPE, "exposure": -.5, "sharpen": 0, "denoise": 0}, apply_crop=False)
        self.assertEqual(rendered.dtype, np.float32)
        self.assertFalse(np.array_equal(rendered[0, 0], rendered[0, 1]))
        self.assertEqual(len(half_float_rgba(source)), 1 * 2 * 4 * 2)

    def test_clipping_stats_detect_channel_recoverable_highlights(self):
        source = LinearImage(np.array([[[1.2, .7, .6], [.2, .2, .2]]], np.float32), 16, "test linear")
        stats = clipping_stats(source, DEFAULT_RECIPE)
        self.assertEqual(stats["highlight_percent"], 50.0)
        self.assertEqual(stats["recoverable_highlight_percent"], 50.0)

    def test_raw_decode_requests_16_bit_linear_highlight_mode(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "sample.RAF"
            raw.write_bytes(b"synthetic raw fixture")

            def fake_run(command, **kwargs):
                output = Path(command[command.index("-Z") + 1])
                cv2.imwrite(str(output), np.full((8, 12, 3), 32768, np.uint16))
                self.assertIn("-4", command)
                self.assertEqual(command[command.index("-H") + 1], "2")
                return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch("engine.subprocess.run", side_effect=fake_run):
                loaded = load_image(raw)
            self.assertEqual(loaded.source_bits, 16)
            self.assertEqual(loaded.source_kind, "RAW linear")


if __name__ == "__main__":
    unittest.main()
