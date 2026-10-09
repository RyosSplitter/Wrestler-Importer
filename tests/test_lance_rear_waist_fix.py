"""Verify rear seam recovery, localized skinning edits and bending behavior."""
import json
from pathlib import Path
import unittest

import numpy as np

from tools.lance_rear_waist_fix import dense, BEND_POSES, pose_checks
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.weight_trial_review import deform


class LanceRearWaistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]/'downloads'
        cls.base=(root/'1800-PSP-hybrid-mirrored-left-waist.pac').read_bytes()
        cls.fixed=(root/'1800-PSP-hybrid-rear-waist-restored.pac').read_bytes()
        cls.report=json.loads((root/'1800-PSP-hybrid-rear-waist-restored-report.json').read_text())
        cls.a=audit_yobj(next(raw for s,raw in sections(cls.base) if s['id']==2))
        cls.b=audit_yobj(next(raw for s,raw in sections(cls.fixed) if s['id']==2))

    def test_six_original_curve_points_are_shared_by_torso_and_trunks(self):
        added=self.report['patch']['added_vertex_records'];self.assertEqual(len(added),12)
        points={tuple(v['position']) for v in added};self.assertEqual(len(points),6)
        expected=[(1.63761,-1.87662,-.57452),(1.12250,-1.78369,-1.10298),(.70557,-1.74211,-1.31226),
                  (-.71719,-1.74144,-1.31228),(-1.13416,-1.78264,-1.10300),(-1.64937,-1.87509,-.57455)]
        for p in expected:self.assertLess(min(np.linalg.norm(np.array(q)-p) for q in points),1e-5)
        for p in points:
            rows=[r for r in added if tuple(r['position'])==p]
            self.assertEqual({r['texture'] for r in rows},{'l-mune2','l-pan1'})
            for r in rows:self.assertEqual(self.b['meshes'][r['mesh']]['vertices'][r['vertex']]['position'],p)

    def test_only_declared_original_weight_and_normal_records_change(self):
        changes={(r['mesh'],r['vertex']) for r in self.report['patch']['changed_weight_normal_records']}
        self.assertEqual(len(changes),12)
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette']);self.assertEqual(a['opaque'],b['opaque'])
            for vi in range(len(a['vertices'])):
                old=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']]
                new=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']];offset=4*a['weight_slots']
                if (a['index'],vi) in changes:
                    self.assertEqual(old[offset:offset+12],new[offset:offset+12])
                    self.assertEqual(old[offset+24:],new[offset+24:])
                else:self.assertEqual(old,new)
            for ma,mb in zip(a['materials'],b['materials']):self.assertEqual(ma['raw'][:132],mb['raw'][:132])
        for key in ('bone_raw','texture_raw','model_descriptor_raw'):self.assertEqual(self.a[key],self.b[key])

    def test_recovered_seam_has_correct_source_weight_profile_and_survives_bends(self):
        names={b['name']:b['index'] for b in self.b['bones']};ps,ws=dense(self.b)
        offsets={};offset=0
        for mesh in self.b['meshes']:offsets[mesh['index']]=offset;offset+=len(mesh['vertices'])
        root=np.float32(.8235290050506592);spine=np.float32(.17647099494934082)
        for r in self.report['patch']['added_vertex_records']:
            row=offsets[r['mesh']]+r['vertex'];expected=np.zeros(len(names))
            expected[names['root']]=root;expected[names['koshi']]=spine
            np.testing.assert_array_equal(ws[row],expected)
        # Confirm this corrects the stale central seam weights, rather than
        # only adding geometry with the previous collapse interpolation.
        center=self.b['meshes'][53]['vertices'][69]
        np.testing.assert_allclose(center['weights'][:2],[root,spine],rtol=0,atol=0)
        self.assertGreater(self.a['meshes'][53]['vertices'][69]['weights'][1],.55)
        poses=pose_checks(self.b,self.report['patch'])
        self.assertEqual(set(poses),set(BEND_POSES))
        for result in poses.values():
            self.assertEqual(result['rear_seam_gap'],0)
            self.assertGreater(result['minimum_rest_vs_skinned_face_normal_cosine'],0)

    def test_file_size_counts_and_unrelated_pac_payloads(self):
        self.assertEqual(len(self.fixed),136*1024)
        for key,delta in [('vertices',12),('triangles',12),('indices',54),('strips',21),('meshes',0),('textures',0),('material_records',0),('bones',0)]:
            self.assertEqual(self.b['report'][key]-self.a['report'][key],delta)
        original=dict((s['id'],raw) for s,raw in sections(self.base));final=dict((s['id'],raw) for s,raw in sections(self.fixed))
        self.assertEqual(original.keys(),final.keys())
        for key in original:
            if key!=2:self.assertEqual(original[key],final[key])


if __name__=='__main__':unittest.main()
