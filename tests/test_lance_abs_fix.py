"""Delivery fixture checks for the in-place abdomen repair."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from tools.lance_abs_fix import run
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections, pose_validation


class LanceAbsFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=Path(__file__).resolve().parents[1]/'downloads'
        cls.base=(folder/'1800-PSP-hybrid-waist-seam-fix.pac').read_bytes()
        cls.final=(folder/'1800-PSP-hybrid-waist-abs-fix.pac').read_bytes()
        cls.report=json.loads((folder/'1800-PSP-hybrid-waist-abs-fix-report.json').read_text())
        cls.old=next(raw for s,raw in sections(cls.base) if s['id']==2)
        cls.new=next(raw for s,raw in sections(cls.final) if s['id']==2)
        cls.a=audit_yobj(cls.old);cls.b=audit_yobj(cls.new)

    def test_binary_change_is_confined_to_reported_uv_and_normal_records(self):
        allowed=set()
        for field,offset,length in [('uv_records',0,8),('normal_records',12,12)]:
            for item in self.report['patch'][field]:
                m=self.a['meshes'][item['mesh']];r=self.a['report']['mesh_reports'][item['mesh']]
                start=r['vertex_buffer_start']+item['vertex']*m['stride']+4*m['weight_slots']+offset
                allowed.update(range(start,start+length))
        changes={i for i,(a,b) in enumerate(zip(self.old,self.new)) if a!=b}
        self.assertEqual(len(self.old),len(self.new))
        self.assertEqual(len(changes),self.report['patch']['changed_bytes'])
        self.assertTrue(changes<=allowed)
        self.assertEqual(self.a['report']['allocations'],self.b['report']['allocations'])
        self.assertEqual(self.a['report']['relocation_locations'],self.b['report']['relocation_locations'])
        self.assertEqual(self.a['header'],self.b['header'])
        self.assertEqual(self.a['bone_raw'],self.b['bone_raw'])
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertEqual(a['materials'],b['materials'])
            self.assertEqual(a['raw_header'],b['raw_header'])
            self.assertEqual(a['raw_palette_header'],b['raw_palette_header'])
            for vi,(av,bv) in enumerate(zip(a['vertices'],b['vertices'])):
                start=vi*a['stride'];length=4*a['weight_slots']
                self.assertEqual(a['raw_vertices'][start:start+length],b['raw_vertices'][start:start+length])
                self.assertEqual(av['color'],bv['color'])
                self.assertEqual(av['position'],bv['position'])

    def test_size_textures_and_pose_positions_are_identical(self):
        self.assertEqual(len(self.final),136*1024)
        self.assertEqual(len(self.final),len(self.base))
        original=dict((s['id'],raw) for s,raw in sections(self.base))
        final=dict((s['id'],raw) for s,raw in sections(self.final))
        self.assertEqual(original.keys(),final.keys())
        for key in original:
            if key!=2:self.assertEqual(original[key],final[key])
        for report in pose_validation(self.a,self.b).values():
            self.assertEqual(report['maximum_position_component_difference'],0)

    def test_reference_patch_scope_and_unit_normals(self):
        uv=self.report['patch']['uv_records'];normals=self.report['patch']['normal_records']
        self.assertEqual({(v['mesh'],v['vertex']) for v in uv},{(53,5),(53,18),(53,23)})
        self.assertEqual(len(normals),82)
        for v in uv:
            self.assertEqual(self.b['meshes'][v['mesh']]['vertices'][v['vertex']]['uv'],tuple(v['after_uv']))
            self.assertLess(v['source_surface_distance'],.15)
        for v in normals:
            n=self.b['meshes'][v['mesh']]['vertices'][v['vertex']]['normal']
            self.assertAlmostEqual(np.linalg.norm(n),1,places=6)

    def test_rejects_unrecognized_source_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source.pac').write_bytes(b'invalid');(root/'base.pac').write_bytes(self.base)
            with self.assertRaisesRegex(ValueError,'pinned'):run(root/'source.pac',root/'base.pac',root/'output')
            self.assertFalse((root/'output').exists())


if __name__=='__main__':unittest.main()
