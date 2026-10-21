import unittest
import numpy as np
from tools.cutout_resample_trial import minify
from model_qa.alpha_coverage import compare


class CutoutResampleTests(unittest.TestCase):
    def test_source_strand_lost_by_nearest_sampling_can_be_rescued(self):
        source=np.zeros((32,32,4),np.uint8);source[2:10,2]=[170,90,30,192];before=source.copy()
        nearest,_=minify(source,(16,16));rescued,report=minify(source,(16,16),preserve_components=True)
        self.assertEqual(compare(source,nearest)['probes']['128']['vanished_components'],1)
        self.assertEqual(compare(source,rescued)['probes']['128']['vanished_components'],0)
        self.assertGreater(len(report['rescued_source_samples']),0)
        for edit in report['rescued_source_samples']:
            x,y=edit['source_xy'];self.assertEqual(edit['source_rgba'],source[y,x].tolist())
        self.assertTrue(set(np.unique(rescued[:,:,3])) <= set(np.unique(source[:,:,3])))
        np.testing.assert_array_equal(source,before)

    def test_unused_source_component_is_not_rescued(self):
        source=np.zeros((32,32,4),np.uint8);source[2:10,2]=[170,90,30,192]
        mask=np.zeros((32,32),bool);mask[16:]=True
        _,r=minify(source,(16,16),mask,preserve_components=True)
        self.assertFalse(r['rescued_source_samples'])

    def test_no_upscaling_and_deterministic(self):
        source=np.zeros((32,32,4),np.uint8);source[2:10,2]=[170,90,30,255]
        a,r1=minify(source,(16,16),preserve_components=True);b,r2=minify(source,(16,16),preserve_components=True)
        np.testing.assert_array_equal(a,b);self.assertEqual(r1,r2)
        with self.assertRaisesRegex(ValueError,'ceiling'):minify(source,(64,32),preserve_components=True)


if __name__=='__main__':unittest.main()
