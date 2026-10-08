import copy
import math
import unittest

from tools.region_mesh import bone_regions, make_regions, pack_regions, quantize_weights, smooth_normals, weight_regions


def skeleton():
    names = [('root', -1), ('koshi', 0), ('mune', 1), ('kubi', 2), ('atama', 3),
             ('r_eye', 4), ('l_sakotsu', 2), ('l_te', 6), ('r_momo', 0), ('r_ashi', 8)]
    return [{'index': i, 'name': n, 'parent': p} for i, (n, p) in enumerate(names)]


def vertex(position, weights):
    return {'position': list(position), 'normal': [0, 0, 1], 'uv': [0, 0],
            'color': [255] * 4, 'weights': list(weights)}


class RegionTests(unittest.TestCase):
    def test_regions_follow_target_ancestry_and_blended_weights(self):
        mapping = bone_regions(skeleton())
        self.assertEqual([mapping[i] for i in (2, 5, 7, 9)], ['Torso', 'Head', 'Arms', 'Legs'])
        scores = weight_regions([0, 0, .1, 0, .2, 0, .3, .4, 0, 0], mapping)
        self.assertAlmostEqual(scores['Arms'], .7)
        self.assertAlmostEqual(scores['Head'], .2)
        with self.assertRaises(ValueError):
            weight_regions([0] * 10, mapping)

    def test_face_classification_uses_psp_weights_preserves_uvs_and_input(self):
        model = {'bones': skeleton(), 'bone_count': 10, 'triangle_count': 1,
                 'meshes': [{'index': 0, 'bone_palette': [4, 7],
                             'vertices': [vertex(p, [.2, .8]) for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0)]],
                             'materials': [{'texture_id': 3, 'triangles': [[0, 1, 2]]}]}]}
        original = copy.deepcopy(model)
        regional = make_regions(model)
        self.assertEqual(model, original)
        self.assertEqual(regional['triangle_count'], 1)
        self.assertEqual(regional['meshes'][0]['region'], 'Arms')
        for v in regional['meshes'][0]['vertices']:
            self.assertAlmostEqual(v['region_strength'], .8)
            self.assertEqual(v['weights'][7], .8)
            self.assertEqual(v['uv'], [0, 0])

    def test_smooth_normals_cross_uv_region_seams_and_respect_detail_groups(self):
        a = [vertex(p, [1]) for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0)]]
        b = [vertex(p, [1]) for p in [(0, 0, 0), (0, 0, 1), (1, 0, 0)]]
        b[0]['uv'] = [1, 1]
        detail = copy.deepcopy(a)
        for v in detail:
            v['smoothing_group'] = 1
        model = {'meshes': [{'vertices': v, 'materials': [{'triangles': [[0, 1, 2]]}]}
                            for v in (a, b, detail)]}
        smooth_normals(model)
        self.assertEqual(a[0]['normal'], b[0]['normal'])
        for x, y in zip(a[0]['normal'], [0, 1/math.sqrt(2), 1/math.sqrt(2)]):
            self.assertAlmostEqual(x, y)
        self.assertEqual(detail[0]['normal'], [0, 0, 1])

    def test_palette_packing_keeps_normalized_shared_seam_weights_and_geometry(self):
        weights = [.1, .2, .3, .4, 0, 0, 0, 0, 0, 0]
        meshes = []
        for region, points in [('Head', [(0, 0, 0), (1, 0, 0), (0, 1, 0)]),
                               ('Torso', [(0, 0, 0), (0, 0, 1), (1, 0, 0)])]:
            meshes.append({'region': region, 'vertices': [vertex(p, weights) for p in points],
                           'materials': [{'texture_id': 0, 'triangles': [[0, 1, 2]]}]})
        model = {'meshes': meshes, 'preparation_report': {}}
        original = copy.deepcopy(model)
        packed = pack_regions(model, weight_encoding='float')
        self.assertEqual(model, original)
        self.assertEqual(packed['triangle_count'], 2)
        for mesh in packed['meshes']:
            self.assertLessEqual(len(mesh['bone_palette']), 8)
            self.assertEqual(mesh['bone_palette'], [0, 1, 2, 3])
            for v in mesh['vertices']:
                self.assertAlmostEqual(sum(v['weights']), 1)
                self.assertEqual(v['weights'], weights[:4])
        self.assertEqual(packed['preparation_report']['region_weight_packing']['max_mass_removed'], 0)

    def test_psp_fixed_point_weights_sum_to_128_and_bound_error(self):
        for denominator in (128, 32768):
            for weights in ([1.], [.333, .333, .334], [.001, .1, .299, .6], [.125]*8):
                actual = quantize_weights(weights, denominator)
                self.assertEqual(sum(actual), 1.)
                self.assertTrue(all(w*denominator == round(w*denominator) for w in actual))
                self.assertLess(max(abs(a-b) for a, b in zip(weights, actual)), 1/denominator)
        with self.assertRaises(ValueError):
            quantize_weights([0, 0])


if __name__ == '__main__':
    unittest.main()
