"""Procedural checks; no supplied/model game assets are distributed."""
import copy
import struct
import unittest

import numpy as np

from tools.tna_obj_trial import read_obj, fit_sphere, fit_facial_binds, check_bone_changes, enclose_influences, quantize_binding
from tools.prepare_model import bone_matrices


TRIANGLE = '''usemtl test
v 0 0 0
v 1 0 0
v 0 1 0
vt 0 0
vt 1 0
vt 0 1
vn 0 0 1
f 1/1/1 2/2/1 3/3/1
'''


def fixture():
    names = [('root',-1,[0,0,0]),('atama',0,[0,-8,0]),
             ('l_eye',1,[.35,-.65,-1.35]),('r_eye',1,[-.35,-.65,-1.35])]
    bones = []; raw = bytearray(80*len(names))
    for i,(name,parent,pos) in enumerate(names):
        bones.append(dict(index=i,name=name,parent=parent,local_position=pos,rotation=[0,0,0]))
        struct.pack_into('<3f',raw,80*i+16,*pos);struct.pack_into('<i',raw,80*i+48,parent)
    return dict(bones=bones,bone_count=len(bones),bone_raw=bytes(raw))


class TnaObjTests(unittest.TestCase):
    def test_corner_buffers_are_independent_and_v_flip_is_explicit(self):
        m,r = read_obj(TRIANGLE+'vt .25 .75\nf 1/4/1 3/3/1 2/2/1\n')
        v = m['meshes'][0]['vertices']
        self.assertEqual(len(v),4)
        self.assertEqual(v[0]['source_position_index'],v[3]['source_position_index'])
        self.assertEqual(v[0]['position'],v[3]['position'])
        self.assertEqual(v[0]['uv'],[0,1]);self.assertEqual(v[3]['uv'],[.25,.25])
        self.assertFalse(r['source_rig_present'])

    def test_negative_indices_resolve_each_attribute_buffer(self):
        m,_=read_obj(TRIANGLE.replace('1/1/1 2/2/1 3/3/1','-3/-3/-1 -2/-2/-1 -1/-1/-1'))
        self.assertEqual(m['meshes'][0]['materials'][0]['triangles'],[[0,1,2]])

    def test_invalid_indices_are_rejected(self):
        for bad in ('0/1/1','4/1/1','-4/1/1','1/4/1','1//1'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                read_obj(TRIANGLE.replace('1/1/1',bad))

    def test_nonfinite_degenerate_and_untriangulated_input_rejected(self):
        for text in (TRIANGLE.replace('v 0 0 0','v nan 0 0'),
                     TRIANGLE.replace('v 0 1 0','v 2 0 0'),
                     TRIANGLE.replace('3/3/1\n','3/3/1 1/1/1\n')):
            with self.assertRaises(ValueError):read_obj(text)

    def test_materials_not_silently_combined(self):
        with self.assertRaises(ValueError):read_obj(TRIANGLE+'usemtl another\n')

    def test_sphere_fit_recovers_center_and_radius(self):
        center=np.array([.4,-8.6,-.8]);directions=np.vstack((np.eye(3),-np.eye(3)))
        actual,radius,error=fit_sphere(center+.17*directions)
        np.testing.assert_allclose(actual,center,atol=1e-10)
        self.assertAlmostEqual(radius,.17);self.assertLess(error,1e-10)

    def test_planar_eye_fit_is_rejected(self):
        with self.assertRaises(ValueError):fit_sphere([[0,0,0],[1,0,0],[1,1,0],[0,1,0]])

    def test_bind_fit_preserves_body_axes_and_fits_eye_centers(self):
        original=fixture();saved=copy.deepcopy(original)
        centers={'l':np.array([.385,-8.7,-.8]),'r':np.array([-.385,-8.7,-.8])}
        result,report=fit_facial_binds(original,centers)
        self.assertEqual(original,saved)
        self.assertEqual(result['bone_raw'][:160],original['bone_raw'][:160])
        actual=bone_matrices(result)
        for i,side in [(2,'l'),(3,'r')]:
            np.testing.assert_allclose(actual[i,:3,3],centers[side],atol=1e-6)
            self.assertEqual(result['bones'][i]['rotation'],original['bones'][i]['rotation'])
        check_bone_changes(original,result,report)

    def test_unapproved_bone_rotation_edit_is_rejected(self):
        original=fixture();result,report=fit_facial_binds(original,{'l':np.array([.35,-8.6,-.8]),'r':np.array([-.35,-8.6,-.8])})
        raw=bytearray(result['bone_raw']);struct.pack_into('<f',raw,2*80+32,.1);result['bone_raw']=bytes(raw)
        with self.assertRaises(ValueError):check_bone_changes(original,result,report)

    def test_incomplete_bind_manifest_is_rejected(self):
        original=fixture();result,report=fit_facial_binds(original,{'l':np.array([.35,-8.6,-.8]),'r':np.array([-.35,-8.6,-.8])})
        report['changed_local_positions'].pop()
        with self.assertRaises(ValueError):check_bone_changes(original,result,report)

    def test_influence_bounds_expand_without_moving_centers_or_binds(self):
        target=fixture();model=copy.deepcopy(target)
        model['meshes']=[dict(vertices=[dict(position=p,weights=[1.,0.,0.,0.]) for p in ([0,0,0],[1,0,0],[0,2,0])],bone_palette=[0,1,2,3])]
        result,changes=enclose_influences(target,model)
        self.assertEqual(len(changes),1)
        self.assertEqual(target['bone_raw'],fixture()['bone_raw'])
        self.assertEqual(result['bone_raw'][:76],target['bone_raw'][:76])
        self.assertEqual(result['bone_raw'][80:],target['bone_raw'][80:])
        self.assertGreater(struct.unpack_from('<f',result['bone_raw'],76)[0],2.)

    def test_new_weight_quantization_normalizes_without_geometry_changes(self):
        target=fixture();model=copy.deepcopy(target);model['textures']=['test']
        model['meshes']=[dict(index=0,bone_palette=[0,1,2,3],vertices=[dict(position=p,normal=[0,0,1],
            uv=[0,0],color=[255]*4,weights=[.25001,.24999,.25,.25]) for p in ([0,0,0],[1,0,0],[0,1,0])],
            materials=[dict(texture_id=0,triangles=[[0,1,2]])])]
        before=copy.deepcopy(model);result,report=quantize_binding(model,512)
        self.assertEqual(model,before)
        for a,b in zip(before['meshes'][0]['vertices'],result['meshes'][0]['vertices']):
            self.assertEqual(a['position'],b['position']);self.assertEqual(a['uv'],b['uv'])
            self.assertEqual(sum(b['weights']),1.)
            self.assertTrue(all(w*512==int(w*512) for w in b['weights']))
        self.assertLessEqual(report['maximum_pose_position_error_height'],report['position_error_height_limit'])


if __name__=='__main__':unittest.main()
