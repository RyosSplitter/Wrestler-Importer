import unittest
import numpy as np
from PIL import Image
from model_qa.palette_quality import compare, representation


class TextureColorQATests(unittest.TestCase):
    def gradient(self):
        image = np.zeros((128, 128, 4), np.uint8); image[:, :, 3] = 255
        image[:, :, :3] = np.arange(128, dtype=np.uint8)[None, :, None] + 64
        return image

    def test_identical_representation_has_no_new_findings(self):
        a = self.gradient(); self.assertFalse(compare(a, a, a)['review'])
        self.assertEqual(representation(a, a)['quantization_rgb_rmse_255'], 0)

    def test_higher_resolution_does_not_hide_palette_regression(self):
        source = self.gradient()
        baseline = np.array(Image.fromarray(source).resize((32, 32), Image.Resampling.LANCZOS))
        candidate = np.array(Image.fromarray(source).resize((64, 64), Image.Resampling.LANCZOS))
        candidate[:, :, :3] = (candidate[:, :, :3] // 32) * 32
        r = compare(source, baseline, candidate, sensitive=True)
        self.assertIn('native-grid-quantization-error-increased', r['findings'])
        self.assertIn('sensitive-page-useful-color-count-reduced', r['findings'])
        self.assertNotIn('resolution-reduced-relative-to-baseline', r['findings'])

    def test_unused_padding_excluded_and_inputs_unchanged(self):
        source = self.gradient(); candidate = source.copy(); candidate[64:, :, :3] = 0
        mask = np.zeros((128, 128), bool); mask[:64] = True; before = source.copy()
        self.assertFalse(compare(source, source, candidate, mask)['review'])
        np.testing.assert_array_equal(source, before)

    def test_alpha_cannot_be_silently_ignored(self):
        source = self.gradient(); source[0, 0, 3] = 0
        with self.assertRaisesRegex(ValueError, 'Opaque'): representation(source, source)

    def test_resolution_reduction_and_source_ceiling_reported(self):
        a = self.gradient(); b = np.array(Image.fromarray(a).resize((64, 64)))
        self.assertIn('resolution-reduced-relative-to-baseline', compare(a, a, b)['findings'])
        c = np.array(Image.fromarray(a).resize((256, 128)))
        self.assertIn('source-resolution-ceiling-exceeded', compare(a, a, c)['findings'])


if __name__ == '__main__': unittest.main()
