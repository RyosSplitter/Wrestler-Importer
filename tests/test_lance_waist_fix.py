"""Verify the delivered waistband patch independently of source reconstruction."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

import numpy as np

from tools.lance_waist_fix import run
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.weight_trial_review import POSES, deform


class LanceWaistFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        downloads=Path(__file__).resolve().parents[1]/'downloads'
        cls.base=(downloads/'1800-PSP-hybrid-half-textures.pac').read_bytes()
        cls.fixed=(downloads/'1800-PSP-hybrid-waist-seam-fix.pac').read_bytes()
        cls.report=json.loads((downloads/'1800-PSP-hybrid-waist-seam-fix-report.json').read_text())
        cls.old=next(raw for s,raw in sections(cls.base) if s['id']==2)
        cls.new=next(raw for s,raw in sections(cls.fixed) if s['id']==2)
        cls.a=audit_yobj(cls.old);cls.b=audit_yobj(cls.new)

    def test_only_explicit_uv_position_and_one_ring_normal_bytes_change(self):
        allowed=set()
        for field,offset,length in [('changed_position_uv_records',0,8),('changed_position_uv_records',24,12),('changed_normal_records',12,12)]:
            for record in self.report['patch'][field]:
                mesh=self.a['meshes'][record['mesh']];r=self.a['report']['mesh_reports'][record['mesh']]
                start=r['vertex_buffer_start']+record['vertex']*mesh['stride']+mesh['weight_slots']*4+offset
                allowed.update(range(start,start+length))
        self.assertEqual(len(self.old),len(self.new))
        self.assertTrue({i for i,(a,b) in enumerate(zip(self.old,self.new)) if a!=b}<=allowed)
        self.assertEqual(self.a['report']['allocations'],self.b['report']['allocations'])
        self.assertEqual(self.a['report']['relocation_locations'],self.b['report']['relocation_locations'])
        self.assertEqual(self.a['header'],self.b['header'])
        self.assertEqual(self.a['bone_raw'],self.b['bone_raw'])

    def test_native_indices_materials_color_alpha_and_weight_bits_stay_identical(self):
        self.assertEqual(len(self.fixed),136*1024)
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            self.assertEqual(a['materials'],b['materials'])
            for i,(av,bv) in enumerate(zip(a['vertices'],b['vertices'])):
                start=i*a['stride'];length=a['weight_slots']*4
                self.assertEqual(a['raw_vertices'][start:start+length],b['raw_vertices'][start:start+length])
                self.assertEqual(av['color'],bv['color'])
        before=dict((s['id'],raw) for s,raw in sections(self.base));after=dict((s['id'],raw) for s,raw in sections(self.fixed))
        self.assertEqual(before[8],after[8]);self.assertEqual(before[9],after[9])

    def test_four_original_seam_points_and_unit_normals(self):
        self.assertEqual(len(self.report['patch']['junctions']),4)
        self.assertEqual(len(self.report['patch']['changed_position_uv_records']),14)
        expected={(1.7637462615966797,-1.9194122552871704,0.021693727001547813),
                  (-1.7755591869354248,-1.9177454710006714,0.02165842056274414),
                  (-0.005761383101344109,-1.6959104537963867,-1.4477211236953735),
                  (-1.0876390933990479,-2.0687711238861084,1.1658153533935547)}
        self.assertEqual({tuple(r['after_position']) for r in self.report['patch']['junctions']},expected)
        for r in self.report['patch']['changed_position_uv_records']:
            self.assertEqual(tuple(self.b['meshes'][r['mesh']]['vertices'][r['vertex']]['position']),tuple(r['after_position']))
        for r in self.report['patch']['changed_normal_records']:
            self.assertAlmostEqual(np.linalg.norm(self.b['meshes'][r['mesh']]['vertices'][r['vertex']]['normal']),1,places=6)

    def test_repaired_seams_remain_coincident_in_all_diagnostic_poses(self):
        model=self.b;points=np.array([v['position'] for m in model['meshes'] for v in m['vertices']]);weights=np.zeros((len(points),len(model['bones'])));row=0
        for mesh in model['meshes']:
            for v in mesh['vertices']:
                for bone,w in zip(mesh['bone_palette'],v['weights']):weights[row,bone]=w
                row+=1
        for name,pose in POSES.items():
            posed=deform(dict(bones=model['bones'],bone_count=len(model['bones'])),points,weights,pose)
            for junction in self.report['patch']['junctions']:
                rows=np.flatnonzero(np.all(points==junction['after_position'],axis=1))
                self.assertGreater(len(rows),1)
                self.assertEqual(float(np.max(np.abs(posed[rows]-posed[rows[0]]))),0,(name,rows))

    def test_unrecognized_input_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source.pac').write_bytes(b'not the pinned source');(root/'base.pac').write_bytes(self.base)
            with self.assertRaisesRegex(ValueError,'pinned'):run(root/'source.pac',root/'base.pac',root/'output')
            self.assertFalse((root/'output').exists())


if __name__=='__main__':unittest.main()
