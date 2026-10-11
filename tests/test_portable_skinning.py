"""Portable compatibility policy and PAC-level preservation using generated data."""
import struct
import unittest

from desktop.core import Request,validate_pac
from desktop.skinning import adapt_yobj,apply_single_slot_compatibility
from tools.generate_conformance_fixtures import vectors,pac
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections


def one_slot_model():
    m=audit_yobj(vectors()['psp-quad.yobj'])
    record=bytearray(m['bone_raw'][:80]);record[:16]=b'extra'.ljust(16,b'\0')
    struct.pack_into('<i',record,76,0)
    m['bone_raw']+=record
    header=bytearray(m['header']);struct.pack_into('<I',header,28,3);m['header']=bytes(header)
    row=m['meshes'][0];stride=row['stride'];slots=row['weight_slots']
    row['raw_vertices']=b''.join(struct.pack('<f',1.)+row['raw_vertices'][i*stride+4*slots:(i+1)*stride]
                                for i in range(len(row['vertices'])))
    row.update(bone_palette=[0],stride=40,weight_slots=1)
    return write_model(m,[[0]])


class PortableSkinningTests(unittest.TestCase):
    def test_general_one_slot_policy_has_exact_native_and_pose_semantics(self):
        before=one_slot_model();after,r=adapt_yobj(before)
        native=audit_yobj(after)
        self.assertEqual(native['meshes'][0]['stride'],48)
        self.assertEqual(native['meshes'][0]['bone_palette'],[0,1,2])
        self.assertEqual(r['added_vertex_buffer_bytes'],32)
        self.assertTrue(all(v['weights']==[1.,0.,0.] for v in native['meshes'][0]['vertices']))
        self.assertTrue(r['preservation']['per_bone_nonzero_weight_bits_identical'])
        self.assertEqual(r['poses']['status'],'pass')

    def test_two_slot_layout_is_not_generalized_without_evidence(self):
        raw=vectors()['psp-quad.yobj'];after,r=adapt_yobj(raw)
        self.assertEqual(raw,after);self.assertEqual(r['changed_meshes'],[])

    def test_multiple_model_sections_and_unrelated_payloads_are_preserved(self):
        source=one_slot_model();f=vectors();tex=next(raw for s,raw in sections(f['psp-quad.pac']) if s['id']==9)
        before=pac([(2,source),(9,tex),(26,source),(50,b'opaque untouched')])
        after,r=apply_single_slot_compatibility(before)
        a={s['id']:raw for s,raw in sections(before)};b={s['id']:raw for s,raw in sections(after)}
        self.assertEqual(r['changed_meshes'],2)
        self.assertEqual(r['added_vertex_buffer_bytes'],64)
        self.assertEqual(a[9],b[9]);self.assertEqual(a[50],b[50])
        self.assertEqual(b[2],b[26]);validate_pac(after)
        self.assertEqual(before,pac([(2,source),(9,tex),(26,source),(50,b'opaque untouched')]))

    def test_unchanged_layout_leaves_pac_byte_identical(self):
        raw=vectors()['psp-quad.pac'];after,r=apply_single_slot_compatibility(raw)
        self.assertEqual(raw,after);self.assertEqual(r['changed_meshes'],0)

    def test_budget_failure_is_explicit_and_does_not_mutate_input(self):
        f=vectors();tex=next(raw for s,raw in sections(f['psp-quad.pac']) if s['id']==9)
        before=pac([(2,one_slot_model()),(9,tex)]);saved=bytes(before)
        candidate,_=apply_single_slot_compatibility(before)
        with self.assertRaisesRegex(ValueError,'Export withheld'):
            apply_single_slot_compatibility(before,max_bytes=len(candidate)-1)
        self.assertEqual(before,saved)

    def test_deterministic_and_idempotent(self):
        f=vectors();tex=next(raw for s,raw in sections(f['psp-quad.pac']) if s['id']==9)
        original=pac([(2,one_slot_model()),(9,tex)])
        a,r=apply_single_slot_compatibility(original);b,s=apply_single_slot_compatibility(original)
        self.assertEqual(a,b);self.assertEqual(r,s)
        again,report=apply_single_slot_compatibility(a)
        self.assertEqual(a,again);self.assertEqual(report['changed_meshes'],0)

    def test_option_is_on_by_default_and_requires_boolean(self):
        self.assertTrue(Request('a','b').skin_palette_compatibility)
        self.assertFalse(Request('a','b',skin_palette_compatibility=False).skin_palette_compatibility)
        for value in (1,'true',None):
            with self.assertRaisesRegex(ValueError,'must be a boolean'):
                Request('a','b',skin_palette_compatibility=value).validate()


if __name__=='__main__':unittest.main()
