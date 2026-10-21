import unittest
from pathlib import Path
import struct
import numpy as np
from tools.wwe13_texture_format_trial import exact_indexed4, patch_regular_depths
from tools.psp_mesh_audit import audit_yobj
from desktop.texture_optimizer.candidates import read_gim, write_gim


class TextureFormatTrialTests(unittest.TestCase):
    def source(self, count):
        indices = (np.arange(1024).reshape(32, 32) % count).astype(np.uint8)
        palette = np.zeros((256, 4), np.uint8); palette[:, 3] = 255; palette[:, 0] = np.arange(256)
        return write_gim(indices, palette, 8)

    def test_indexed4_is_exact_for_sixteen_actual_colors(self):
        raw = self.source(16); out = exact_indexed4(raw)
        a, p = read_gim(raw); b, q = read_gim(out)
        self.assertEqual(len(q), 16); np.testing.assert_array_equal(p[a], q[b])
        self.assertLess(len(out), len(raw))

    def test_actual_usage_not_declared_palette_controls_eligibility(self):
        raw = self.source(3); self.assertEqual(len(read_gim(exact_indexed4(raw))[1]), 16)

    def test_more_than_sixteen_colors_rejected(self):
        with self.assertRaisesRegex(ValueError, '16 actual'): exact_indexed4(self.source(17))

    def test_alpha_pages_rejected(self):
        a, p = read_gim(self.source(16)); p[0, 3] = 0
        with self.assertRaisesRegex(ValueError, 'opaque'): exact_indexed4(write_gim(a, p, 8))

    def test_native_material_patch_roundtrip_preserves_entire_geometry(self):
        raw = (Path(__file__).parent / 'fixtures/hctp_psp/psp-quad.yobj').read_bytes()
        converted, report = patch_regular_depths(raw, {'skin': 8})
        a, b = audit_yobj(raw), audit_yobj(converted)
        self.assertEqual(b['meshes'][0]['materials'][0]['control'], 7)
        self.assertEqual(a['meshes'][0]['raw_vertices'], b['meshes'][0]['raw_vertices'])
        self.assertEqual(a['meshes'][0]['materials'][0]['strips'], b['meshes'][0]['materials'][0]['strips'])
        self.assertTrue(report['all_other_native_bytes_exact'])
        restored, _ = patch_regular_depths(converted, {'skin': 4})
        self.assertEqual(restored, raw)

    def test_cutout_depth_changes_and_missing_contracts_are_rejected(self):
        raw = (Path(__file__).parent / 'fixtures/hctp_psp/psp-quad.yobj').read_bytes()
        model = audit_yobj(raw)
        start = next(a['start'] for a in model['report']['allocations'] if a['kind'] == 'mesh 0 materials')
        changed = bytearray(raw); struct.pack_into('<I', changed, start + 24, 0x115)
        with self.assertRaisesRegex(ValueError, 'Cutout'):
            patch_regular_depths(bytes(changed), {'skin': 8})
        with self.assertRaisesRegex(ValueError, 'Every texture'):
            patch_regular_depths(raw, {})


if __name__ == '__main__': unittest.main()
