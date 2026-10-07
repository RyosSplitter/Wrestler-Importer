import struct
import unittest

from tools.psp_materials import material_control, regular_template, validate_material_controls


def record(control, tint=128):
    data = bytearray(144)
    data[:4] = bytes([tint, tint, tint, 255])
    struct.pack_into('<I', data, 24, control)
    return bytes(data)


class PSPMaterialTests(unittest.TestCase):
    def test_overlay_only_part_uses_regular_template_and_keeps_complete_record(self):
        ordinary, overlay, indexed8 = record(5), record(0x115), record(7, 150)
        base = [[ordinary, indexed8], [overlay]]
        self.assertEqual(regular_template(base, 1, 4), ordinary)
        self.assertEqual(regular_template(base, 1, 8), indexed8)
        self.assertEqual(base[1], [overlay])

    def test_prefers_matching_part_and_refuses_missing_depth(self):
        other, preferred = record(5, 128), record(5, 140)
        self.assertEqual(regular_template([[other], [preferred]], 1, 4), preferred)
        with self.assertRaises(ValueError):
            regular_template([[record(0x115)]], 0, 4)
        with self.assertRaises(ValueError):
            regular_template([[other]], 0, 8)

    def test_rejects_body_using_blood_flags_and_mismatched_native_color_depth(self):
        model = {'textures': ['bn_dou'], 'meshes': [{'materials': [{'texture_id': 0, 'control': 0x115}]}]}
        with self.assertRaisesRegex(ValueError, 'bn_dou'):
            validate_material_controls(model, [4])
        model['meshes'][0]['materials'][0]['control'] = 5
        validate_material_controls(model, [4])
        with self.assertRaises(ValueError):
            validate_material_controls(model, [8])
        model['meshes'][0]['materials'][0]['control'] = 7
        validate_material_controls(model, [8])

    def test_actual_base_blood_material_is_allowed_only_for_observed_effect(self):
        model = {'textures': ['blood_b'], 'meshes': [{'materials': [{'texture_id': 0, 'control': 0x115}]}]}
        validate_material_controls(model, [4])
        with self.assertRaises(ValueError):
            validate_material_controls(model, [8])
        with self.assertRaises(ValueError):
            material_control(bytes(143))


if __name__ == '__main__':
    unittest.main()
