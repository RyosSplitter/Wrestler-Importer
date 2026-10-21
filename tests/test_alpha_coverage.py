import unittest
import numpy as np
from model_qa.alpha_coverage import compare


class AlphaCoverageTests(unittest.TestCase):
    def test_identical_alpha_is_not_flagged(self):
        image = np.zeros((32, 32, 4), np.uint8); image[3:24, 7:10, 3] = 255
        r = compare(image, image.copy())
        self.assertFalse(r['review'])
        self.assertEqual(r['probes']['128']['thin_edge_support_recall'], 1.)

    def test_equal_total_coverage_can_hide_vanished_strand(self):
        source = np.zeros((64, 64, 4), np.uint8); source[5:10, 5, 3] = 255
        candidate = source.copy(); candidate[:, :, 3] = 0; candidate[5:10, 8, 3] = 255
        r = compare(source, candidate)
        self.assertLess(r['alpha_mae'], 1.)
        p = r['probes']['128']
        self.assertEqual(p['candidate_visible_texels'], p['source_visible_texels'])
        self.assertEqual(p['support_recall'], 0.)
        self.assertEqual(p['vanished_components'], 1)
        self.assertTrue(r['review'])

    def test_unused_padding_does_not_change_used_region_scores(self):
        source = np.zeros((32, 32, 4), np.uint8); source[3:12, 3:7, 3] = 255
        candidate = source.copy(); candidate[20:28, 20:28, 3] = 255
        mask = np.zeros((32, 32), bool); mask[:16, :16] = True
        r = compare(source, candidate, mask)
        self.assertFalse(r['review']); self.assertEqual(r['alpha_mae'], 0.)

    def test_probes_keep_fractional_alpha_and_inputs_unchanged(self):
        source = np.zeros((16, 16, 4), np.uint8); source[2:8, 2:8, 3] = 100
        before = source.copy(); candidate = source.copy(); candidate[2:8, 2:8, 3] = 0
        r = compare(source, candidate)
        self.assertEqual(r['probes']['64']['support_recall'], 0.)
        self.assertIsNone(r['probes']['128']['support_recall'])
        np.testing.assert_array_equal(source, before)

    def test_upscaling_and_invalid_masks_are_reported(self):
        source = np.zeros((16, 16, 4), np.uint8)
        result = compare(source, np.zeros((32, 16, 4), np.uint8))
        self.assertTrue(result['source_quality_ceiling_exceeded'])
        self.assertTrue(result['review'])
        with self.assertRaises(ValueError): compare(source, source, np.zeros((16, 16), bool))


if __name__ == '__main__': unittest.main()
