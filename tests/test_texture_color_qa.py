import unittest
import numpy as np
from model_qa.texture_color import lab,color_metrics


class ColorQATests(unittest.TestCase):
    def test_known_lab_white_and_black(self):
        np.testing.assert_allclose(lab(np.array([[255.,255.,255.],[0.,0.,0.]])),[[100.,0.,0.],[0.,0.,0.]],atol=3e-5)
    def test_identical_colors_have_zero_error(self):
        im=np.full((32,32,4),100,np.uint8);im[:,:,3]=255
        r=color_metrics(im,im,np.ones((32,32),bool))
        self.assertEqual(r['delta_e76_p95'],0);self.assertFalse(r['review'])
    def test_local_discoloration_not_hidden_by_global_mean(self):
        a=np.full((32,32,4),255,np.uint8);a[:16,:,:3]=[180,100,70];a[16:,:,:3]=[70,100,180]
        b=a[::-1].copy();r=color_metrics(a,b,np.ones((32,32),bool))
        np.testing.assert_allclose(r['rgb_mean_bias'],[0.,0.,0.]);self.assertGreater(r['maximum_local_tile_lab_bias'],20);self.assertTrue(r['review'])
    def test_unused_padding_does_not_affect_result(self):
        a=np.full((32,32,4),255,np.uint8);b=a.copy();b[:16,:,:3]=0;mask=np.zeros((32,32),bool);mask[16:]=True
        self.assertFalse(color_metrics(a,b,mask)['review'])
    def test_empty_region_is_unknown_not_zero_error(self):
        im=np.full((32,32,4),255,np.uint8)
        with self.assertRaises(ValueError):color_metrics(im,im,np.zeros((32,32),bool))


if __name__=='__main__':unittest.main()
