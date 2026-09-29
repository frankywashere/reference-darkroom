import unittest
import numpy as np
from engine import _clone_layers

class CloneTests(unittest.TestCase):
    def test_linear_clone_layers(self):
        src=np.zeros((100,100,3),np.float32);src[:,:50]=4
        stroke=dict(size=.3,feather=0,flow=100,opacity=100,offset=[-.5,0],sample='original',points=[[.75,.5]])
        layer=dict(enabled=True,opacity=100,strokes=[stroke])
        out=_clone_layers(src,[layer])
        self.assertEqual(out[50,75,0],4)
        np.testing.assert_array_equal(src[50,75],0)
        np.testing.assert_array_equal(out[:20],src[:20])
        np.testing.assert_array_equal(_clone_layers(src,[dict(layer,enabled=False)]),src)
        self.assertEqual(_clone_layers(src,[dict(layer,opacity=50)])[50,75,0],2)
        erase=dict(stroke,erase=True)
        np.testing.assert_array_equal(_clone_layers(src,[dict(layer,strokes=[stroke,erase])]),src)
        edge=dict(stroke,offset=[1,0])
        np.testing.assert_array_equal(_clone_layers(src,[dict(layer,strokes=[edge])]),src)
        second=dict(stroke,offset=[.5,0],points=[[.25,.8]],sample='stack')
        self.assertTrue(np.isfinite(_clone_layers(src,[layer,dict(layer,strokes=[second])])).all())

if __name__=='__main__':unittest.main()
