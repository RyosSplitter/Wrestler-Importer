import copy
import unittest

import numpy as np

from tools.pac_inspect import FormatError
from tools.prepare_model import Surface, donor_bone_map, prepare, similarity_fit


def model():
    bones = []
    for i, (name, point) in enumerate(zip(('root', 'koshi', 'atama', 'l_te', 'r_te'),
                                         ((0, 0, 0), (0, 0, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0)))):
        bones.append({'index': i, 'name': name, 'parent': -1 if i == 0 else 0,
                      'local_position': list(point), 'rotation': [0, 0, 0]})
    vertices = [{'position': list(p), 'normal': [0, 0, 1], 'uv': [p[0], -p[1]],
                 'weights': [0.25, 0.75], 'color': [255] * 4}
                for p in ((0, 0, 0), (1, 0, 0), (0, -1, 0), (1, -1, 0))]
    return {'model_name': 'test', 'bones': bones, 'bone_count': 5, 'textures': ['skin'],
            'texture_count': 1, 'triangle_count': 2, 'geometry_decoded': True,
            'meshes': [{'index': 0, 'bone_palette': [1, 2], 'vertices': vertices,
                        'materials': [{'texture_id': 0, 'triangles': [[0, 1, 2], [1, 3, 2]]}]}]}


class PreparationTests(unittest.TestCase):
    def test_psp_profile_makes_body_vertices_opaque_without_changing_rgb_or_input(self):
        source, target, donor = model(), model(), model()
        colors = [[100, 120, 140, 0], [255, 240, 220, 50],
                  [200, 180, 160, 152], [255, 255, 255, 255]]
        for v, color in zip(source['meshes'][0]['vertices'], colors):
            v['color'] = color
        original = copy.deepcopy(source)
        opaque, report = prepare(source, target, donor)
        raw, raw_report = prepare(source, target, donor, vertex_alpha_policy='source')
        self.assertEqual(source, original)
        for a, b in zip(opaque['meshes'], raw['meshes']):
            self.assertEqual(a['materials'], b['materials'])
            for v, w in zip(a['vertices'], b['vertices']):
                self.assertEqual(v['color'][:3], w['color'][:3])
                self.assertEqual(v['color'][3], 255)
                self.assertEqual(v['source_vertex_alpha'], w['color'][3])
                for attribute in ('position', 'normal', 'uv', 'weights'):
                    self.assertEqual(v[attribute], w[attribute])
        self.assertEqual(report['vertex_alpha']['changed_vertices'], 3)
        self.assertEqual(report['vertex_alpha']['after_histogram'], {255: 4})
        self.assertEqual(raw_report['vertex_alpha']['before_histogram'], {0: 1, 50: 1, 152: 1, 255: 1})
        self.assertEqual(raw_report['vertex_alpha']['changed_vertices'], 0)
        with self.assertRaises(FormatError):
            prepare(source, target, donor, vertex_alpha_policy='unknown')

    def test_similarity_recovers_scale_rotation_translation(self):
        source = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        target = 2.5 * source @ rotation.T + [4, 2, -3]
        scale, actual_rotation, translation = similarity_fit(source, target)
        np.testing.assert_allclose(scale * source @ actual_rotation.T + translation, target, atol=1e-12)
        self.assertAlmostEqual(scale, 2.5)
        self.assertAlmostEqual(np.linalg.det(actual_rotation), 1)

    def test_collinear_alignment_rejected(self):
        with self.assertRaises(FormatError):
            similarity_fit([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 0, 0], [1, 0, 0], [2, 0, 0]])

    def test_compact_weight_budget_reports_removed_mass_and_keeps_skeleton(self):
        source, target, donor = model(), model(), model()
        reduced, report = prepare(source, target, donor, max_influences=1, max_palette=1)
        self.assertEqual(reduced['triangle_count'], 2)
        self.assertEqual(reduced['bones'], target['bones'])
        self.assertEqual(report['weight_transfer']['max_weight_mass_removed_for_top1'], 0.25)
        for mesh in reduced['meshes']:
            self.assertEqual(mesh['bone_palette'], [2])
            self.assertTrue(all(v['weights'] == [1] for v in mesh['vertices']))
        with self.assertRaises(FormatError):
            prepare(source, target, donor, max_influences=4, max_palette=2)

    def test_nearest_triangle_returns_barycentric_projection_and_edge(self):
        surface = Surface(model())
        index, bary, distance = surface.nearest([0.2, -0.3, 2])
        self.assertAlmostEqual(distance, 2)
        actual = bary @ surface.triangles[index]
        np.testing.assert_allclose(actual, [0.2, -0.3, 0], atol=1e-12)
        index, bary, distance = surface.nearest([2, 0, 0])
        self.assertAlmostEqual(distance, 1)
        self.assertTrue(np.all(bary >= 0))

    def test_missing_helper_bones_collapse_by_parent_name(self):
        donor, target = model(), model()
        donor['bones'].append({'index': 5, 'name': 'helper', 'parent': 2})
        mapping, collapsed = donor_bone_map(donor, target)
        self.assertEqual(mapping[5], 2)
        self.assertEqual(collapsed, {'helper': 'atama'})

    def test_preparation_keeps_faces_skeleton_weights_and_originals(self):
        source, target, donor = model(), model(), model()
        originals = copy.deepcopy((source, target, donor))
        prepared, report = prepare(source, target, donor)
        self.assertEqual((source, target, donor), originals)
        self.assertEqual(prepared['bones'], target['bones'])
        self.assertEqual(prepared['triangle_count'], 2)
        self.assertLess(report['alignment']['landmark_rms'], 1e-12)
        self.assertLessEqual(report['max_bones_per_mesh'], 8)
        for mesh in prepared['meshes']:
            for vertex in mesh['vertices']:
                self.assertAlmostEqual(sum(vertex['weights']), 1)
                self.assertEqual(vertex['weights'], [0.25, 0.75])
                self.assertIn(vertex['uv'][1], (0, 1))


if __name__ == '__main__':
    unittest.main()
