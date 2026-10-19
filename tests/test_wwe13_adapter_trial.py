"""Game-asset-free checks for the isolated conversion experiment."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from tools.wwe13_adapter_trial import bone_role, rotation_between, source_bundle, chart_atlas, ocular_transfer
from tools.sym_atlas import bilinear


class Wwe13AdapterTests(unittest.TestCase):
    def test_body_root_and_spine_semantics(self):
        self.assertEqual(bone_role('Bip Pelvis', set()), 'root')
        self.assertEqual(bone_role('Bip Spine', set()), 'koshi')
        self.assertEqual(bone_role('Bip Spine1', set()), 'mune')

    def test_each_digit_keeps_side_and_segment(self):
        for side in ('L', 'R'):
            for digit in range(5):
                for suffix, target_suffix in (('', '0'), ('1', '1'), ('2', '2')):
                    self.assertEqual(bone_role(f'Bip {side} Finger{digit}{suffix}', set()),
                                     f'{side.lower()}_yubi{digit}{target_suffix}')

    def test_helpers_are_explicit_not_substring_guesses(self):
        self.assertEqual(bone_role('R_Wrist_x2', set()), 'r_kote_x')
        self.assertEqual(bone_role('L_Chest_Dummy', set()), 'mune')
        self.assertIsNone(bone_role('UnrelatedHeadThing', set()))

    def test_rotation_preserves_lengths_and_handedness(self):
        a, b = np.array([1., .3, -.2]), np.array([1., 0., 0.])
        r = rotation_between(a, b)
        np.testing.assert_allclose(r.T @ r, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(r), 1.)
        np.testing.assert_allclose(r @ (a / np.linalg.norm(a)), b, atol=1e-12)

    def test_unknown_source_fails_before_discovery(self):
        with self.assertRaises(ValueError):
            source_bundle(b'EPAC' + bytes(4096))

    def test_chart_pages_shared_across_source_meshes(self):
        vertices = [dict(position=[float(i), 0., 0.], normal=[0., 0., 1.],
                         uv=uv, weights=[1.], color=[255]*4) for i, uv in enumerate(([.2,.2],[.3,.2],[.2,.3]))]
        mesh = dict(index=0, vertices=vertices, materials=[dict(texture_id=0, triangles=[[0,1,2]])])
        model = dict(meshes=[mesh, dict(copy.deepcopy(mesh), index=1)], textures=['atlas'], texture_count=1)
        original = copy.deepcopy(model)
        image = np.random.default_rng(12).integers(0, 256, (256,256,4), dtype=np.uint8)
        result, crops, report = chart_atlas(model, [image])
        self.assertEqual(len(crops), 1)
        self.assertEqual(model, original)
        for old, new in zip(model['meshes'], result['meshes']):
            self.assertEqual([v['position'] for v in old['vertices']], [v['position'] for v in new['vertices']])
            before = bilinear(image, [v['uv'] for v in old['vertices']])
            after = bilinear(crops[0], [v['uv'] for v in new['vertices']])
            np.testing.assert_allclose(before, after, atol=1e-6)

    def ocular_case(self, source_weights, donor_weights):
        names = ['l_eye', 'r_eye', 'l_mabuta', 'r_mabuta', 'atama', 'd_kuchi']
        bones = [dict(name=n, index=i) for i, n in enumerate(names)]
        vertex = dict(position=[0.,0.,0.], normal=[0.,0.,1.], uv=[.5,.5], color=[255]*4, weights=source_weights)
        source = dict(bones=bones, meshes=[dict(vertices=[vertex])])
        target = dict(bones=bones, bone_count=len(bones))
        with patch('tools.weight_trial_review.transfer', return_value=(np.array([donor_weights]), {})):
            return ocular_transfer(source, source, target)

    def test_rigid_eye_rejects_donor_lid_role_without_amplifying_eye(self):
        model, report = self.ocular_case([1.,0.,0.,0.,0.,0.], [.2,0.,.6,0.,.2,0.])
        np.testing.assert_allclose(model['meshes'][0]['vertices'][0]['weights'], [.2,0.,0.,0.,.8,0.])
        self.assertEqual(report['rigid_eyeball_eyelid_influences_introduced'], 0)

    def test_ocular_transfer_preserves_jaw_mass_exactly(self):
        model, report = self.ocular_case([.6,0.,0.,0.,0.,.4], [.2,0.,.6,0.,.2,0.])
        np.testing.assert_allclose(model['meshes'][0]['vertices'][0]['weights'], [.12,0.,0.,0.,.48,.4])
        self.assertTrue(report['nonocular_coefficients_exact'])

    def test_no_cross_eye_donor_spill(self):
        model, _ = self.ocular_case([1.,0.,0.,0.,0.,0.], [0.,1.,0.,0.,0.,0.])
        self.assertEqual(model['meshes'][0]['vertices'][0]['weights'], [0.,0.,0.,0.,1.,0.])

    def test_palette_ignores_unoccupied_saturated_atlas_context(self):
        from tools.wwe13_texture_trial import encode_occupied
        from desktop.texture_optimizer.candidates import read_gim
        source = np.full((64,64,4), 255, np.uint8)
        source[:,:,:3] = [255, 0, 255]
        source[24:40,24:40,:3] = [150, 100, 75]
        mask = np.zeros((64,64), float); mask[24:40,24:40] = .5
        row = encode_occupied(source, (64,64), 4, 16, mask)
        indices, palette = read_gim(row['raw'])
        self.assertTrue(np.all(palette[indices][24:40,24:40,:3] == [150,100,75]))
        self.assertEqual(row['entry']['used_palette_colors'], 1)

    def test_occupied_palette_does_not_upscale(self):
        from tools.wwe13_texture_trial import encode_occupied
        with self.assertRaises(ValueError):
            encode_occupied(np.full((32,32,4),255,np.uint8), (64,64), 4, 16, np.ones((32,32)))

    def test_cranial_padding_adds_only_zero_influences(self):
        from tools.wwe13_trial import pad_cranial_palettes
        target = dict(bones=[dict(index=i,name=n) for i,n in enumerate(['atama','d_kuchi','kubi'])])
        model = dict(meshes=[dict(index=0,bone_palette=[0,1],vertices=[dict(weights=[.7,.3])])])
        result, report = pad_cranial_palettes(model, target)
        self.assertEqual(result['meshes'][0]['bone_palette'], [0,1,2])
        self.assertEqual(result['meshes'][0]['vertices'][0]['weights'], [.7,.3,0.])
        self.assertEqual(model['meshes'][0]['bone_palette'], [0,1])


if __name__ == '__main__':
    unittest.main()
