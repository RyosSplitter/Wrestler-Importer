import copy
import unittest
import numpy as np
from model_qa.surface_attributes import compare


def fixture():
    mesh = dict(index=0, bone_palette=[0], vertices=[dict(position=p, uv=uv, weights=[1.])
                for p, uv in zip([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]], [[0.,0.],[.9,0.],[0.,.9]])],
                materials=[dict(texture_id=0, triangles=[[0,1,2]])])
    y, x = np.indices((32,32))
    image = np.stack([x*8, y*8, (x+y)*4, np.full_like(x,255)],axis=2).astype(np.uint8)
    return dict(bones=[dict(index=0,name='root',parent=-1)], meshes=[mesh], textures=['page']), {'page': image}


class SurfaceAttributeTests(unittest.TestCase):
    def test_record_reordering_does_not_create_uv_error(self):
        source, images = fixture(); target = copy.deepcopy(source)
        m = target['meshes'][0]; m['vertices'] = m['vertices'][::-1]
        m['materials'][0]['triangles'] = [[2,1,0]]
        r = compare(source, target, images, samples=200)
        self.assertLess(r['overall']['source_texel_displacement']['maximum'], 1e-10)
        self.assertFalse(r['overall']['review'])

    def test_uv_warp_is_detected_when_geometry_is_identical(self):
        source, images = fixture(); target = copy.deepcopy(source)
        for v in target['meshes'][0]['vertices']:
            v['uv'][0] += .25
        r = compare(source, target, images, samples=200)
        self.assertAlmostEqual(r['overall']['source_texel_displacement']['p95'], 8.)
        self.assertLess(r['overall']['surface_distance']['maximum'], 1e-10)
        self.assertGreater(r['overall']['original_texture_placement_rgb_rmse_255'], 10.)
        self.assertTrue(r['overall']['review'])

    def test_missing_original_images_are_not_silently_ignored(self):
        source, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'Missing original'):
            compare(source, source, {}, samples=20)


if __name__ == '__main__':
    unittest.main()
