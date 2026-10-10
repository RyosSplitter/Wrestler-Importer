"""Regression checks against all three actual Jericho weight versions."""
import copy
import json
from pathlib import Path
import unittest
import zipfile

import numpy as np

from model_qa.geometry import geometry
from model_qa.ocular import evaluate,probes,skin
from tools.jericho_eye_guard_trial import repair,frozen_attributes,OCULAR
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections

class JerichoEyeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.old_raw=next(raw for s,raw in sections((root/'downloads/0600-PSP-hybrid-Jericho.pac').read_bytes()) if s['id']==2)
        with zipfile.ZipFile(root/'downloads/Jericho-QA-facial-weights-experiment.zip') as z:
            cls.jaw_raw=z.read('trial/candidate.yobj')
            cls.source=json.loads(z.read('trial/input-source-weighted.json'))
        cls.fixed_raw,cls.trace=repair(cls.old_raw,cls.jaw_raw)
        cls.a,cls.b,cls.c=map(audit_yobj,(cls.old_raw,cls.jaw_raw,cls.fixed_raw))
        cls.eye_report=evaluate(cls.source,cls.a,cls.b,cls.c)

    def test_known_bad_eye_motion_is_detected_and_candidate_passes(self):
        r=self.eye_report
        self.assertEqual(r['status'],'pass');self.assertEqual(len(r['poses']),16)
        self.assertEqual(sum(p['jaw_experiment_flagged'] for p in r['poses'].values()),14)
        self.assertGreater(r['poses']['eyes-world-x-25']['jaw_experiment_vs_previous_eye_motion']['maximum'],.17)
        for p in r['poses'].values():
            self.assertTrue(p['candidate_passes'])
            self.assertEqual(p['candidate_vs_previous_eye_motion']['maximum'],0)
            self.assertEqual(p['outside_selected_max_delta'],0)
            self.assertEqual(p['jaw_preservation_max_delta'],0)

    def test_only_ocular_records_change_and_source_jaw_fix_is_retained(self):
        a,b,c=map(geometry,(self.a,self.b,self.c))
        ids=[i for i,n in enumerate(b.bone_names) if n in OCULAR]
        selected=b.weights[:,ids].sum(1)>1e-7
        self.assertEqual(int(selected.sum()),99);self.assertEqual(self.trace['changed_records'],84)
        np.testing.assert_array_equal(c.weights[selected],a.weights[selected])
        np.testing.assert_array_equal(c.weights[~selected],b.weights[~selected])
        self.assertEqual(len(self.trace['palette_changes']),4)
        frozen_attributes(self.b,self.c)
        self.assertTrue(self.c['report']['offsets_ranges_indices_palettes_weights_valid'])

    def test_repair_is_deterministic_and_inputs_are_immutable(self):
        old,jaw=self.old_raw,self.jaw_raw
        fixed,trace=repair(old,jaw)
        self.assertEqual(fixed,self.fixed_raw);self.assertEqual(trace,self.trace)
        self.assertEqual(old,self.old_raw);self.assertEqual(jaw,self.jaw_raw)
        for mesh in self.c['meshes']:self.assertLessEqual(len(mesh['bone_palette']),8)

    def test_reverting_all_facial_weights_fails_jaw_regression_check(self):
        with self.assertRaisesRegex(ValueError,'jaw motion regressed'):
            evaluate(self.source,self.a,self.b,self.a)

    def test_unverified_source_position_correspondence_is_rejected(self):
        broken=copy.deepcopy(self.source)
        for mesh in broken['meshes']:
            for v in mesh['vertices']:v['position'][0]+=.01
        with self.assertRaisesRegex(ValueError,'correspondence was not verified'):
            evaluate(broken,self.a,self.b,self.c)

    def test_local_controller_probes_cover_translation_and_missing_brows(self):
        self.assertTrue(any('translate' in c for p in probes().values() for c in p['controls'].values()))
        source=geometry(self.source)
        _,unsupported=skin(source,probes()['psp-brow-local'])
        self.assertEqual(unsupported,['l_mayu_02','r_mayu_02'])
        self.assertIsNone(self.eye_report['poses']['psp-brow-local']['original_own_rig_vs_candidate'])

if __name__=='__main__':unittest.main()
