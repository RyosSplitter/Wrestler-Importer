"""Regression checks on the accepted Jericho PAC and archived source stage."""
import copy
import json
from pathlib import Path
import unittest
import zipfile

from tools.jericho_elbow_guard_trial import repair, signature, TEXTURE
from tools.jericho_elbow_review import evaluate
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from model_qa.pipeline import POSES


class JerichoElbowGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.pac=(root/'downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST.pac').read_bytes()
        cls.raw=next(r for s,r in sections(cls.pac) if s['id']==2)
        with zipfile.ZipFile(root/'downloads/Jericho-QA-facial-weights-experiment.zip') as z:
            cls.source=json.loads(z.read('trial/corrected-weight-transfer.json'))
        # Source passthrough is the reference contract of the worker's opt-in
        # preservation path. The separate trial archives the actual Blender run.
        cls.fixed,cls.trace=repair(cls.raw,cls.source,cls.source)
        cls.before,cls.after=map(audit_yobj,(cls.raw,cls.fixed))
        cls.qa=evaluate(cls.source,cls.before,cls.after,samples=2000)

    def test_original_pad_surface_uvs_weights_and_winding_are_restored(self):
        self.assertNotEqual(signature(self.source,TEXTURE),signature(self.before,TEXTURE))
        self.assertEqual(signature(self.source,TEXTURE),signature(self.after,TEXTURE))
        self.assertEqual(self.trace['before_pad_triangles'],69)
        self.assertEqual(self.trace['source_pad_triangles'],73)
        self.assertEqual(self.after['report']['vertices'],self.before['report']['vertices']+2)
        self.assertEqual(self.after['report']['triangles'],self.before['report']['triangles']+4)

    def test_pad_motion_improves_and_all_boundary_aliases_stay_joined(self):
        self.assertEqual(self.qa['status'],'pass')
        self.assertEqual(len(self.trace['shared_skin_records']),3)
        for p in self.qa['pad_poses'].values():
            self.assertEqual(p['source_boundary_groups'],21)
            self.assertGreater(p['before']['p95'],.001)
            self.assertLess(p['after']['maximum'],1e-6)
            self.assertLess(p['maximum_pad_skin_seam_gap'],1e-6)

    def test_accepted_eye_jaw_neck_motion_is_exact(self):
        self.assertEqual(len(self.qa['eye_jaw_neck_probes']),16)
        for p in self.qa['eye_jaw_neck_probes'].values():
            self.assertEqual(p['maximum_delta_vs_accepted'],0)
        self.assertEqual(len(self.qa['full_suite_facial_identity']),len(POSES))
        for p in self.qa['full_suite_facial_identity'].values():
            self.assertEqual(p['facial_neck_maximum_delta'],0)

    def test_unrelated_native_meshes_and_all_palettes_are_exact(self):
        for a,b in zip(self.before['meshes'],self.after['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            self.assertEqual(a['opaque'],b['opaque'])
            if a['index'] not in (27,28):
                self.assertEqual(a['raw_vertices'],b['raw_vertices'])
                for x,y in zip(a['materials'],b['materials']):self.assertEqual(x['strips'],y['strips'])
        for field in ('bone_raw','texture_raw','model_descriptor_raw'):
            self.assertEqual(self.before[field],self.after[field])
        self.assertTrue(self.after['report']['offsets_ranges_indices_palettes_weights_valid'])

    def test_nonpreserving_guard_is_rejected(self):
        bad=copy.deepcopy(self.source)
        bad['meshes'][8]['vertices'][11]['position'][0]+=.01
        with self.assertRaisesRegex(ValueError,'Guarded decimation changed'):
            repair(self.raw,self.source,bad)

    def test_repair_is_deterministic_and_source_is_immutable(self):
        source=copy.deepcopy(self.source)
        fixed,trace=repair(self.raw,source,source)
        self.assertEqual(fixed,self.fixed);self.assertEqual(trace,self.trace)
        self.assertEqual(source,self.source)


if __name__=='__main__':unittest.main()
