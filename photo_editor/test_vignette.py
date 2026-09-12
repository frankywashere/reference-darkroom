import unittest
import numpy as np
from engine import _finish, normalize_recipe


class VignetteTests(unittest.TestCase):
    def test_old_range_preserved(self):
        yy=np.linspace(-1,1,101,dtype=np.float32)[:,None]
        xx=np.linspace(-1,1,101,dtype=np.float32)[None,:]
        edge=np.clip((np.sqrt(xx*xx+yy*yy)-.25)/1.1,0,1)**1.6
        for amount in [0,15,50,100]:
            image=np.ones((101,101,3),dtype=np.float32)*.8
            expected=image*(1-edge[...,None]*(amount/100)*.65)
            np.testing.assert_allclose(_finish(image,normalize_recipe({'vignette':amount}),0),expected,atol=1e-7)

    def test_stronger_monotonic_center_unchanged(self):
        previous=None
        for amount in [0,50,100,125,150,200]:
            result=_finish(np.ones((101,101,3),dtype=np.float32)*.8,normalize_recipe({'vignette':amount}),0)
            self.assertTrue(np.isfinite(result).all());self.assertGreaterEqual(result.min(),0)
            self.assertAlmostEqual(float(result[50,50,0]),.8,places=6)
            if previous is not None:self.assertTrue((result<=previous+1e-7).all())
            previous=result
        self.assertLess(result[0,0,0],.02)
