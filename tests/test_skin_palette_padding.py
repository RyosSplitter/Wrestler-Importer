"""Independent native round-trip checks with the synthetic two-bone quad."""
import copy
from pathlib import Path
import struct
import unittest

from experiments.skin_palette_padding import pad_mesh,exact_pose_checks
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model,verify


class SlotPaddingTests(unittest.TestCase):
    def setUp(self):
        self.model=audit_yobj(Path('tests/fixtures/hctp_psp/psp-quad.yobj').read_bytes())
        m=self.model['meshes'][0];old=m['weight_slots']
        m['raw_vertices']=b''.join(struct.pack('<f',1.)+m['raw_vertices'][i*m['stride']+old*4:(i+1)*m['stride']]
                                  for i in range(len(m['vertices'])))
        m.update(bone_palette=[0],weight_slots=1,stride=40)
        for v in m['vertices']:v['weights']=[1.]
        self.before=write_model(self.model,[[0]]);self.model=audit_yobj(self.before)

    def test_zero_slot_round_trip_preserves_all_effective_semantics(self):
        model=copy.deepcopy(self.model)
        model['meshes'][0]=pad_mesh(model['meshes'][0],model['bones'],2)
        after=write_model(model,[[0]]);decoded=audit_yobj(after)
        self.assertEqual(decoded['meshes'][0]['bone_palette'],[0,1])
        self.assertEqual(decoded['meshes'][0]['stride'],44)
        self.assertTrue(all(v['weights']==[1.,0.] for v in decoded['meshes'][0]['vertices']))
        self.assertTrue(verify(self.before,after,[[0]])['per_bone_nonzero_weight_bits_identical'])
        self.assertEqual(exact_pose_checks(self.model,decoded)['status'],'pass')

    def test_input_model_and_attribute_bits_are_preserved(self):
        m=self.model['meshes'][0];before=copy.deepcopy(m)
        padded=pad_mesh(m,self.model['bones'],2)
        self.assertEqual(m,before)
        for i in range(len(m['vertices'])):
            self.assertEqual(m['raw_vertices'][i*40+4:(i+1)*40],padded['raw_vertices'][i*44+8:(i+1)*44])

    def test_invalid_slot_counts_or_missing_distinct_bones_are_refused(self):
        for n in (1,3,9):
            with self.assertRaises(ValueError):pad_mesh(self.model['meshes'][0],self.model['bones'],n)

    def test_rigid_and_non_float_layouts_are_refused(self):
        m=copy.deepcopy(self.model['meshes'][0]);m['rigid']=True
        with self.assertRaises(ValueError):pad_mesh(m,self.model['bones'],2)
        m['rigid']=False;m['base_flag']=0x15ff
        with self.assertRaises(ValueError):pad_mesh(m,self.model['bones'],2)


if __name__=='__main__':unittest.main()
