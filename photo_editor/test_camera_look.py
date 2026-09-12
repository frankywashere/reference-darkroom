import unittest
import numpy as np
from camera_look import fit_tone
from engine import DEFAULT_RECIPE, normalize_recipe, _tone


class CameraLookTests(unittest.TestCase):
    def test_fit_and_toggle(self):
        values=np.geomspace(.002,1.4,12000).reshape(100,120)
        raw=np.repeat(values[...,None],3,axis=2).astype(np.float32)
        target=.18*(raw/.18)**.8*2**.45
        profile=fit_tone(raw,target)
        self.assertAlmostEqual(profile['ev'],.45,places=4)
        self.assertAlmostEqual(profile['gamma'],.8,places=4)
        recipe=normalize_recipe({'camera_look':profile,'camera_look_enabled':True})
        result=_tone(raw,recipe)
        np.testing.assert_allclose(result,target,rtol=1e-4)
        recipe['camera_look_enabled']=False
        np.testing.assert_array_equal(_tone(raw,recipe),_tone(raw,DEFAULT_RECIPE))
        self.assertGreater(float(result.max()),1)  # No baked-in white clipping.

    def test_flat_rejected(self):
        with self.assertRaises(ValueError):fit_tone(np.ones((8,8,3))*.1,np.ones((8,8,3))*.2)

    def test_recipe_persists(self):
        r=normalize_recipe({'camera_look_enabled':True,'camera_look':{'ev':.5,'gamma':.8}})
        self.assertTrue(r['camera_look_enabled']);self.assertEqual(r['camera_look']['ev'],.5)


if __name__=='__main__':unittest.main()
