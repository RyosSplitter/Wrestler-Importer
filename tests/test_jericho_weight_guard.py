"""Weight-stage and frozen-native-geometry checks for the independent trial."""
import copy
import io
import json
from pathlib import Path
import unittest
import zipfile

import numpy as np

from model_qa.geometry import geometry
from tools.jericho_hybrid_trial import prepare_hybrid
from tools.jericho_weight_guard_trial import replay
from tools.psp_mesh_audit import audit_yobj,digest
from tools.psp_mesh_merge_trial import sections
from tools.weight_trial_review import descendant_names


class JerichoWeightGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.z=zipfile.ZipFile(cls.root/'downloads/Jericho-QA-facial-weights-experiment.zip')
        cls.pac=(cls.root/'downloads/0600-PSP-hybrid-Jericho.pac').read_bytes()
        cls.raw=next(r for s,r in sections(cls.pac) if s['id']==2)
        cls.new=cls.z.read('trial/candidate.yobj');cls.a=audit_yobj(cls.raw);cls.b=audit_yobj(cls.new)
        cls.before=json.loads(cls.z.read('before/report.json'));cls.after=json.loads(cls.z.read('after/report.json'))
        cls.gate=json.loads(cls.z.read('acceptance.json'))

    @classmethod
    def tearDownClass(cls):cls.z.close()

    def test_opt_in_stage_retains_source_weights_and_legacy_default(self):
        source=json.loads(self.z.read('trial/input-source-weighted.json'));target=json.loads(self.z.read('trial/input-psp-donor.json'))
        old=prepare_hybrid(source,target);fixed=prepare_hybrid(source,target,preserve_source_cranial=True)
        archived_old=json.loads(self.z.read('trial/legacy-weight-transfer.json'));archived_new=json.loads(self.z.read('trial/corrected-weight-transfer.json'))
        # Windows/Linux BLAS differ by ~1e-14 in this float64 interpolation.
        # The tolerance is far below one serialized float32 weight ULP.
        np.testing.assert_allclose(geometry(old).weights,geometry(archived_old).weights,atol=2e-13,rtol=0)
        np.testing.assert_array_equal(geometry(fixed).weights,geometry(archived_new).weights)
        np.testing.assert_array_equal(geometry(old).vertices,geometry(fixed).vertices)
        with np.load(io.BytesIO(self.z.read('trial/weight-comparison.npz'))) as w:
            np.testing.assert_allclose(geometry(fixed).weights,w['mapped_source_weights'],atol=1e-7)
            g=geometry(fixed);head=[i for i,n in enumerate(g.bone_names) if n in descendant_names(fixed,'atama')]
            outside=w['mapped_source_weights'][:,head].sum(1)==0
            np.testing.assert_array_equal(w['legacy_hybrid_weights'][outside],w['corrected_weights'][outside])

    def test_replay_is_reproducible_without_input_mutation(self):
        stage=json.loads(self.z.read('trial/corrected-weight-transfer.json'));snapshot=copy.deepcopy(stage)
        raw,_=replay(self.raw,stage)
        self.assertEqual(raw,self.new);self.assertEqual(stage,snapshot)
        self.assertEqual(digest(self.pac),self.gate['structure']['baseline_pac_sha256'])

    def test_native_geometry_attributes_indices_and_render_state_are_exact(self):
        self.assertEqual(len(self.a['meshes']),len(self.b['meshes']))
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertLessEqual(len(b['bone_palette']),8)
            self.assertEqual(len(a['vertices']),len(b['vertices']))
            for i in range(len(a['vertices'])):
                self.assertEqual(a['raw_vertices'][i*a['stride']+4*a['weight_slots']:(i+1)*a['stride']],b['raw_vertices'][i*b['stride']+4*b['weight_slots']:(i+1)*b['stride']])
            for x,y in zip(a['materials'],b['materials']):
                self.assertEqual(x['strips'],y['strips']);self.assertEqual(x['raw'][:132],y['raw'][:132])
        for k in ('bone_raw','texture_raw','model_descriptor_raw'):self.assertEqual(self.a[k],self.b[k])

    def test_all_regions_all_poses_pass_unchanged_tolerances_and_rest_metrics(self):
        self.assertEqual(len(self.after['poses']),12);self.assertEqual(len(self.after['rest']['regions']),15)
        self.assertEqual(self.before['thresholds'],self.after['thresholds'])
        self.assertEqual(self.before['rest'],self.after['rest'])
        self.assertEqual(self.after['flags'],[])
        self.assertEqual(self.gate['status'],'eligible-for-human-review')
        self.assertEqual(self.gate['new_flags'],[]);self.assertEqual(self.gate['regressions'],[])
        for m in self.gate['improvements']:self.assertLess(m['after_p95_height'],.3*m['before_p95_height'])
        self.assertTrue(self.gate['structure']['native_audit_passed'])
        self.assertLessEqual(self.gate['structure']['projected_existing_layout_pac_bytes'],148000)

    def test_archive_integrity_preview_identity_and_no_pac_written(self):
        self.assertIsNone(self.z.testzip());self.assertFalse(any(n.lower().endswith('.pac') for n in self.z.namelist()))
        self.assertEqual(self.z.read('preview/candidate.yobj'),self.new)
        self.assertFalse(self.gate['structure']['pac_written'])
        report=json.loads(self.z.read('trial/experiment.json'))
        self.assertGreater(len(report['weight_changes']),500)
        self.assertLess(report['maximum_replay_pruned_mass'],1e-7)


if __name__=='__main__':unittest.main()
