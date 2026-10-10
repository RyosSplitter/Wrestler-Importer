import copy
import unittest

import numpy as np

from desktop.precision import bounded_precision,ocular_positions,validate_native_precision,POSITION_ERROR_LIMIT
from tools.generate_conformance_fixtures import vectors
from tools.psp_mesh_audit import audit_yobj


class PrecisionTests(unittest.TestCase):
    def model(self):
        model = audit_yobj(vectors()['psp-quad.yobj'])
        for mesh in model['meshes']:
            for v in mesh['vertices']:
                v['position'] = [p+.1234567 for p in v['position']]
                v['uv'] = [p+.01234567 for p in v['uv']]
                v['normal'] = [.2,.3,float(np.sqrt(.87))]
        return model

    def test_attributes_are_bounded_and_eye_records_are_exact(self):
        model = self.model()
        original = copy.deepcopy(model)
        held = {tuple(model['meshes'][0]['vertices'][0]['position'])}
        result,report = bounded_precision(model,held)
        self.assertEqual(model,original)
        self.assertEqual(result['meshes'][0]['vertices'][0],model['meshes'][0]['vertices'][0])
        self.assertEqual(report['held_ocular_vertex_records'],1)
        self.assertGreater(report['changed_vertex_records']['position'],0)
        self.assertLessEqual(report['maximum_position_error_height'],POSITION_ERROR_LIMIT)
        for a,b in zip(model['meshes'],result['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            self.assertEqual(a['materials'],b['materials'])
            for va,vb in zip(a['vertices'],b['vertices']):
                self.assertEqual(va['weights'],vb['weights'])
                self.assertEqual(va['color'],vb['color'])
        self.assertEqual(model['bone_raw'],result['bone_raw'])
        self.assertEqual(model['texture_raw'],result['texture_raw'])

    def test_original_controller_support_selects_native_coordinates(self):
        control = dict(bones=[dict(index=0,name='atama'),dict(index=1,name='l_eye')],
                       meshes=[dict(bone_palette=[1,0],vertices=[
                           dict(position=[1,2,3],weights=[.01,.99]),
                           dict(position=[4,5,6],weights=[0.,1.])])])
        self.assertEqual(ocular_positions(control),{(1,2,3)})

    def test_new_collapsed_faces_are_rejected(self):
        model = self.model()
        vertices = model['meshes'][0]['vertices']
        vertices[0]['position'] = [0.,0.,0.]
        vertices[1]['position'] = [1e-8,0.,0.]
        with self.assertRaisesRegex(ValueError,'collapsed or flipped'):
            bounded_precision(model,set())

    def test_zero_normals_and_unapproved_precision_are_rejected(self):
        model = self.model()
        with self.assertRaises(ValueError):bounded_precision(model,set(),128)
        model['meshes'][0]['vertices'][1]['normal'] = [0.,0.,0.]
        with self.assertRaisesRegex(ValueError,'zero normal'):bounded_precision(model,set())

    def test_native_validation_rejects_changed_weights_and_rendering(self):
        before = audit_yobj(vectors()['psp-quad.yobj'])
        after = copy.deepcopy(before)
        after['meshes'][0]['vertices'][0]['weights'] = [.25,.75]
        with self.assertRaisesRegex(ValueError,'weights'):
            validate_native_precision(before,after,set())
        after = copy.deepcopy(before)
        material = after['meshes'][0]['materials'][0]
        raw = bytearray(material['raw']);raw[24]^=0x10;material['raw']=bytes(raw)
        with self.assertRaisesRegex(ValueError,'material/draw'):
            validate_native_precision(before,after,set())


if __name__ == '__main__':
    unittest.main()
