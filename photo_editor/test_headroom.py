import unittest
import numpy as np
from headroom import summarize

class SensorTests(unittest.TestCase):
    def test_thresholds_and_cfa_channels(self):
        raw=np.array([[100,1100,600,101],[99,1099,103,350]],dtype=np.uint16)
        colors=np.array([[0,1,0,1],[1,0,1,0]],dtype=np.uint8)
        s=summarize(raw,colors,[100]*4,[1100]*4)
        self.assertEqual(s['saturated_percent'],12.5)
        self.assertEqual(s['at_black_percent'],25)
        self.assertEqual(s['weak_signal_percent'],25)
        self.assertEqual(s['within_one_stop_percent'],25)
        self.assertEqual(len(s['channels']),2)
        self.assertIsNone(s['channels'][0]['dark_variation_dn'])

    def test_black_frame_does_not_claim_headroom_or_noise(self):
        raw=np.zeros((70,70),np.uint16)
        s=summarize(raw,np.zeros_like(raw),[0]*4,[1023]*4)
        self.assertEqual(s['at_black_percent'],100)
        self.assertIsNone(s['channels'][0]['p999_headroom_ev'])
        self.assertIsNone(s['channels'][0]['dark_signal_variation_ratio'])

    def test_per_channel_levels_and_no_mutation(self):
        raw=np.array([[900,900],[500,500]],np.uint16);before=raw.copy()
        s=summarize(raw,np.array([[0,1],[0,1]],np.uint8),[100]*4,[900,1000,1000,1000])
        self.assertEqual(s['saturated_percent'],25)
        np.testing.assert_array_equal(raw,before)

    def test_unsupported_and_invalid_calibration(self):
        with self.assertRaises(ValueError):summarize(np.zeros((2,2,3)),np.zeros((2,2)),[0]*4,[10]*4)
        with self.assertRaises(ValueError):summarize(np.zeros((2,2)),np.zeros((2,2)),[10]*4,[10]*4)

    def test_noise_proxy_has_enough_samples_and_is_finite(self):
        rng=np.random.default_rng(3)
        raw=np.clip(100+rng.normal(35,3,(700,700)),0,65535).astype(np.uint16)
        s=summarize(raw,np.zeros_like(raw),[100]*4,[10000]*4)
        self.assertGreater(s['channels'][0]['dark_pairs'],128)
        self.assertAlmostEqual(s['channels'][0]['dark_variation_dn'],3,delta=.8)
        self.assertGreater(s['channels'][0]['dark_signal_variation_ratio'],5)

if __name__=='__main__':unittest.main()
