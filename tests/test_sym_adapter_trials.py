import copy
import struct
import unittest
from unittest.mock import patch

import numpy as np

from tools.sym_atlas import bilinear, partition
from tools.sym_rig import arrays, bounds_probe, prepare_trial,guard_ocular_support


def model(uv=None):
    uv = uv or [[.45,.2], [.6,.2], [.45,.45], [.6,.45]]
    bones = [dict(index=i, name=name, parent=-1, local_position=[0.,0.,0.],
                  rotation=[0.,0.,0.]) for i, name in enumerate(('root','mune','helper'))]
    vertices = [dict(position=[float(i%2),float(i//2),0.], normal=[0.,0.,1.],
        uv=list(u), color=[255,255,255,255], weights=[.2,.3,.5],
        source_vertex_index=i, original_source_influences=[[0,.2],[1,.3],[2,.5]])
        for i,u in enumerate(uv)]
    return dict(bone_count=3, bones=bones, texture_count=1, textures=['atlas'],
        mesh_count=1, source_vertex_count=4, vertex_count=4, triangle_count=2,
        meshes=[dict(index=0, bone_palette=[0,1,2], vertices=vertices,
            materials=[dict(texture_id=0,triangles=[[0,1,2],[2,1,3]],strips=[])])])


class AtlasPartitionTests(unittest.TestCase):
    def image(self):
        rng = np.random.default_rng(9182)
        return rng.integers(0,256,(64,128,4),dtype=np.uint8)

    def test_cross_tile_faces_preserved_without_clipping(self):
        source = model()
        original = copy.deepcopy(source)
        rgba = self.image()
        before = rgba.copy()
        result, crops, report = partition(source, rgba)
        self.assertEqual(source,original)
        np.testing.assert_array_equal(rgba,before)
        self.assertEqual(result['triangle_count'],2)
        self.assertEqual(report['output_triangles'],2)
        self.assertFalse(report['triangle_clipping'])
        self.assertFalse(report['vertices_moved'])
        self.assertLess(report['maximum_sample_rgba_error'],1e-7)
        self.assertEqual(len(crops),1)
        for a,b in zip(source['meshes'][0]['vertices'],result['meshes'][0]['vertices']):
            for key in ('position','normal','weights','color','source_vertex_index','original_source_influences'):
                self.assertEqual(a[key],b[key])
        self.assertTrue(all(c.shape[0]<=64 and c.shape[1]<=128 for c in crops))

    def test_wrapped_atlas_and_alpha_samples_preserved(self):
        source = model([[.99,.1],[1.04,.1],[.99,.4],[1.04,.4]])
        result, crops, report = partition(source,self.image())
        self.assertLess(report['maximum_sample_rgba_error'],1e-7)
        self.assertEqual(len(crops),1)
        self.assertTrue(all(np.isfinite(v['uv']).all() for m in result['meshes'] for v in m['vertices']))

    def test_deterministic_and_zero_length_uv_edges_do_not_join(self):
        source = model()
        m = source['meshes'][0]
        m['vertices'] += copy.deepcopy(m['vertices'][:2])
        for i,u in enumerate([[.1,.1],[.1,.1],[.2,.3],[.4,.3],[.1,.1],[.1,.1]]):
            m['vertices'][i]['uv']=u
        m['materials'][0]['triangles']=[[0,1,2],[4,5,3]]
        a,ca,ra=partition(source,self.image())
        b,cb,rb=partition(source,self.image())
        self.assertEqual(a,b)
        self.assertEqual(ra,rb)
        self.assertEqual(len(ca),2)
        for x,y in zip(ca,cb):np.testing.assert_array_equal(x,y)

    def test_unknown_layout_and_invalid_uv_fail_closed(self):
        for source in (model([[0,0],[4,0],[0,.5],[4,.5]]),model()):
            if source['meshes'][0]['vertices'][1]['uv'][0] != 4:
                source['meshes'][0]['vertices'][0]['uv'][0]=float('nan')
            rgba=np.tile(self.image(),(1,8,1)) if source['meshes'][0]['vertices'][1]['uv'][0]==4 else self.image()
            with self.assertRaises(ValueError):partition(source,rgba)
        source=model();source['texture_count']=2
        with self.assertRaises(ValueError):partition(source,self.image())

    def test_full_source_axis_repeat_and_wide_patch(self):
        source=model([[.1,-.01],[.2,-.01],[.1,1.01],[.2,1.01]])
        _,_,report=partition(source,self.image())
        self.assertLess(report['maximum_sample_rgba_error'],1e-7)
        wide=np.tile(self.image(),(2,8,1))
        source=model([[.1,.1],[.27,.1],[.1,.9],[.27,.9]])
        _,_,report=partition(source,wide)
        self.assertEqual(report['islands'][0]['dimensions'][0],256)
        self.assertEqual(report['islands'][0]['full_size_native_bits'],[4])
        self.assertLess(report['maximum_sample_rgba_error'],1e-7)

    def test_bilinear_texel_centers_and_repeat(self):
        image=np.arange(16,dtype=np.uint8).reshape(2,2,4)
        np.testing.assert_array_equal(bilinear(image,[[.25,.25],[1.25,.25]]),[image[0,0],image[0,0]])
        np.testing.assert_array_equal(bilinear(image,[[.5,.5]]),[image.mean((0,1))])


class RigTrialTests(unittest.TestCase):
    def target(self):
        target=model();target['bones'][2]['name']='atama';target['model_name']='test'
        return target

    def test_unverified_weights_use_donor_without_ancestor_guess(self):
        source=model();old=copy.deepcopy(source);target=self.target()
        donor=np.array([[0.,0.,1.]]*4)
        with patch('tools.sym_rig.align_reference',return_value=(copy.deepcopy(source),{})), \
             patch('tools.sym_rig.transfer',return_value=(donor,{'test_donor':True})):
            result,report=prepare_trial(source,target)
        self.assertEqual(source,old)
        _,w=arrays(result)
        np.testing.assert_allclose(w,[[.2,.3,.5]]*4)
        self.assertEqual(report['donor_affected_records'],4)
        self.assertEqual(report['maximum_four_influence_pruned_mass'],0.)
        self.assertNotIn('atama',report['direct_body_name_hypothesis'])
        for a,b in zip(source['meshes'][0]['vertices'],result['meshes'][0]['vertices']):
            self.assertEqual(a['original_source_influences'],b['original_source_influences'])
            self.assertEqual(a['position'],b['position'])

    def test_unknown_method_and_invalid_source_sums_rejected(self):
        source=model()
        with self.assertRaises(ValueError):prepare_trial(source,self.target(),method='production')
        source['meshes'][0]['vertices'][0]['weights']=[0.,0.,0.]
        with patch('tools.sym_rig.align_reference',return_value=(source,{})),self.assertRaises(ValueError):
            prepare_trial(source,self.target())

    def test_sphere_probe_does_not_treat_bound_center_as_joint_origin(self):
        source=model()
        for b in source['bones']:b['local_position']=[10.,0.,0.]
        raw=bytearray(72+80*3)
        struct.pack_into('<I',raw,40,64)
        for i in range(3):struct.pack_into('<4f',raw,72+80*i+64,.5,.5,0.,1.)
        report=bounds_probe(raw,source)
        self.assertEqual(report['active_bones'],3)
        self.assertEqual(report['enclosing_active_bones'],3)
        self.assertGreater(report['maximum_center_origin_distance'],9.)

    def test_ocular_spill_removed_and_jaw_lids_preserved(self):
        source=dict(bones=[dict(name='atama',index=0),dict(name='l_eye',index=1),dict(name='r_eye',index=2)])
        target=dict(bones=[dict(name=n,index=i) for i,n in enumerate(['atama','l_eye','r_eye','l_mabuta','d_kuchi'])])
        sw=np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        weights=np.array([[.1,.4,0.,.2,.3],[1.,0.,0.,0.,0.],[1.,0.,0.,0.,0.]])
        before=weights.copy()
        result,r=guard_ocular_support(source,target,sw,weights)
        np.testing.assert_array_equal(result[0],[.5,0.,0.,.2,.3])
        np.testing.assert_array_equal(result[1],[0.,1.,0.,0.,0.])
        np.testing.assert_array_equal(result[2],[0.,0.,1.,0.,0.])
        np.testing.assert_array_equal(weights,before)
        np.testing.assert_array_equal(result[:,4],before[:,4])
        self.assertTrue(r['jaw_coefficients_exact'])
        self.assertEqual(r['source_eye_records'],2)

    def test_nonrigid_or_overlapping_eye_support_requires_review(self):
        bones=[dict(name=n,index=i) for i,n in enumerate(['atama','l_eye','r_eye'])]
        for sw in (np.array([[.5,.5,0.]]),np.array([[0.,.5,.5]])):
            with self.assertRaises(ValueError):
                guard_ocular_support(dict(bones=bones),dict(bones=bones),sw,np.array([[1.,0.,0.]]))


if __name__=='__main__':unittest.main()
