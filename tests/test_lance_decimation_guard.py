"""Portable isolated-patch, regression and native-format checks."""
import copy
import io
import json
from pathlib import Path
import unittest
import zipfile

import numpy as np

from tools.lance_decimation_guard_trial import replay
from tools.psp_mesh_audit import audit_yobj,digest
from tools.psp_mesh_merge_trial import sections
from tools.qa_experiment_review import compare


class LanceGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.z=zipfile.ZipFile(cls.root/'downloads/Lance-QA-decimation-experiment.zip')
        cls.pac=(cls.root/'downloads/1800-PSP-hybrid-source-pelvis-restored.pac').read_bytes()
        cls.raw=next(r for s,r in sections(cls.pac) if s['id']==2)
        cls.changed=cls.z.read('trial/candidate.yobj');cls.a=audit_yobj(cls.raw);cls.b=audit_yobj(cls.changed)
        cls.e=json.loads(cls.z.read('trial/experiment.json'));cls.g=json.loads(cls.z.read('acceptance.json'))

    @classmethod
    def tearDownClass(cls):cls.z.close()

    def test_worker_output_replay_is_deterministic_and_preserves_input(self):
        guarded=json.loads(self.z.read('evidence/guarded-reduction.json'))
        snapshot=copy.deepcopy(guarded)
        result,_=replay(self.raw,guarded)
        self.assertEqual(guarded,snapshot)
        self.assertEqual(result,self.changed)
        self.assertEqual(digest(self.pac),self.g['structure']['baseline_pac_sha256'])
        self.assertFalse(self.g['structure']['pac_written'])

    def test_only_guarded_surface_and_necessary_boundary_positions_change(self):
        moved={(r['mesh'],r['vertex']) for r in self.e['boundary_correspondence']}
        normals=set(map(tuple,self.e['normal_records']))
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            for i in range(len(a['vertices'])):
                x=a['raw_vertices'][i*a['stride']:(i+1)*a['stride']];y=b['raw_vertices'][i*b['stride']:(i+1)*b['stride']];o=4*a['weight_slots']
                self.assertEqual(x[:o+12],y[:o+12])
                if (a['index'],i) not in moved:self.assertEqual(x[o+24:],y[o+24:])
                if (a['index'],i) not in normals:self.assertEqual(x[o+12:o+24],y[o+12:o+24])
            for x,y in zip(a['materials'],b['materials']):
                self.assertEqual(x['raw'][:132],y['raw'][:132])
                if self.a['texture_names'][x['texture_id']] not in self.e['posterior_materials']:self.assertEqual(x['strips'],y['strips'])
        self.assertEqual(len(self.e['retained_superior_seam']),1)
        for key in ('bone_raw','texture_raw','model_descriptor_raw'):self.assertEqual(self.a[key],self.b[key])

    def test_complete_qa_known_defects_improve_without_new_failures(self):
        before=json.loads(self.z.read('before/report.json'));after=json.loads(self.z.read('after/report.json'))
        self.assertEqual(len(after['poses']),12)
        self.assertEqual(len(after['rest']['regions']),15)
        self.assertEqual(self.g['status'],'eligible-for-human-review')
        self.assertEqual(self.g['new_flags'],[]);self.assertEqual(self.g['regressions'],[])
        for r in ('buttocks','pelvis'):
            self.assertGreater(before['rest']['regions'][r]['distance']['p95_height'],.01)
            self.assertLess(after['rest']['regions'][r]['distance']['p95_height'],1e-7)
        self.assertLess(after['rest']['regions']['buttocks']['views']['back']['inward_depth_p95_height'],.002)
        self.assertEqual(before['thresholds'],after['thresholds'])
        self.assertEqual(len(self.g['unchanged_region_sampling_reviews']),1)
        proof=self.g['unchanged_region_sampling_reviews'][0]
        self.assertTrue(proof['identical_posed_position_and_bone_weight_signatures'])
        self.assertTrue(proof['identical_fixed_reference_sample_errors'])
        self.assertEqual(proof['local_triangles'],593)
        self.assertTrue(self.g['structure']['native_audit_passed']);self.assertLessEqual(self.g['structure']['projected_existing_layout_pac_bytes'],148000)

    def test_regression_gate_rejects_worsening_an_already_flagged_region(self):
        before=json.loads(self.z.read('before/report.json'));after=json.loads(self.z.read('after/report.json'));bad=copy.deepcopy(after)
        bad['rest']['regions']['neck']['distance']['p95_height']=.02
        result=compare(before,bad,self.g['structure'],[('buttocks','rest')])
        self.assertEqual(result['status'],'rejected')
        self.assertTrue(any(x['region']=='neck' for x in result['regressions']))

    def test_no_pac_in_bundle_and_geometry_bounds_contain_buffers(self):
        self.assertIsNone(self.z.testzip());self.assertFalse(any(n.lower().endswith('.pac') for n in self.z.namelist()))
        import struct
        for m in self.b['meshes']:
            bounds=np.array(struct.unpack_from('<4f',m['raw_header'],48))
            self.assertLessEqual(max(np.linalg.norm(np.array(v['position'])-bounds[:3]) for v in m['vertices']),bounds[3]+1e-6)


if __name__=='__main__':unittest.main()
