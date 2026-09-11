import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from gpu_io import source_pixels, save_jpg


class GPUTransportTests(unittest.TestCase):
    def test_float32_transport_dimensions_and_values(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.png';Image.new('RGB',(12,8),'white').save(source)
            buf,w,h,bits,kind=source_pixels(str(source),100)
            self.assertEqual((w,h,bits),(12,8,8))
            self.assertEqual(len(buf),12*8*16)
            self.assertTrue(np.allclose(np.frombuffer(buf,dtype='<f4'),1))
            with self.assertRaises(ValueError):source_pixels(str(source),5)

    def test_jpg_orientation_profile_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.jpg';Image.new('RGB',(4,4),'green').save(source)
            original=source.read_bytes()
            rgba=np.zeros((4,4,4),np.uint8);rgba[:2,:,0]=255;rgba[2:,:,2]=255;rgba[:,:,3]=255
            out=save_jpg(rgba.tobytes(),4,4,str(source),td,'',100)
            self.assertNotEqual(out,str(source));self.assertEqual(source.read_bytes(),original)
            im=Image.open(out);self.assertTrue(im.info.get('icc_profile'))
            self.assertGreater(im.getpixel((0,0))[0],240);self.assertGreater(im.getpixel((0,3))[2],240)
            again=save_jpg(rgba.tobytes(),4,4,str(source),td,'',100)
            self.assertNotEqual(again,out)
            with self.assertRaises(ValueError):save_jpg(b'',4,4,str(source),td,'EDIT_',95)
            with self.assertRaises(ValueError):save_jpg(rgba.tobytes(),4,4,str(source),td,'../',95)
