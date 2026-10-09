"""Delivery checks for posterior shape recovery without a whole-body rebuild."""
from collections import Counter
import json
from pathlib import Path
import unittest
import zipfile

import numpy as np

from tools.lance_anatomy_restore import animation_checks, oriented_face_key
from tools.psp_mesh_audit import audit_yobj, digest
from tools.psp_mesh_merge_trial import sections


class LanceAnatomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]/'downloads'
        cls.base=(cls.root/'1800-PSP-hybrid-rear-waist-restored.pac').read_bytes()
        cls.fixed=(cls.root/'1800-PSP-hybrid-source-pelvis-restored.pac').read_bytes()
        cls.report=json.loads((cls.root/'1800-PSP-hybrid-source-pelvis-restored-report.json').read_text())
        cls.raw_a=next(r for s,r in sections(cls.base) if s['id']==2)
        cls.raw_b=next(r for s,r in sections(cls.fixed) if s['id']==2)
        cls.a=audit_yobj(cls.raw_a);cls.b=audit_yobj(cls.raw_b)

    def test_posterior_triangles_match_extracted_source_with_winding(self):
        for tid,total in ((4,47),(7,168)):
            faces=Counter(oriented_face_key(m,t) for m in self.b['meshes'] for a in m['materials'] if a['texture_id']==tid for t in a['triangles'])
            self.assertEqual(sum(faces.values()),total)
            actual=digest(b''.join(b''.join(f) for f in sorted(faces.elements())))
            self.assertEqual(actual,self.report['patch']['source_posterior_oriented_face_hashes'][str(tid)])
        for comparison in self.report['source_surface_comparison'].values():
            self.assertGreater(comparison['before']['maximum_surface_distance'],.24)
            self.assertLess(comparison['after']['maximum_surface_distance'],2e-7)

    def test_only_declared_boundary_positions_uvs_and_local_normals_change(self):
        p=self.report['patch'];moved={(r['mesh'],r['vertex']) for r in p['moved_boundary_records']};normals={(r['mesh'],r['vertex']) for r in p['normal_records']}
        self.assertEqual(moved,{(26,13),(27,0),(53,53),(53,81)})
        selected={(r['mesh'],r['material']) for r in p['restored_faces']+p['adjacent_boundary_splits']}
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette']);self.assertEqual(a['opaque'],b['opaque'])
            self.assertEqual(a['raw_header'][48:],b['raw_header'][48:])
            for vi in range(len(a['vertices'])):
                x=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']];y=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']];o=4*a['weight_slots']
                if (a['index'],vi) not in moved:self.assertEqual(x[:o],y[:o])
                else:
                    weights={self.b['bones'][bone]['name']:w for bone,w in zip(b['bone_palette'],b['vertices'][vi]['weights']) if w}
                    self.assertEqual(weights,{'mune':1.0})
                self.assertEqual(x[o+8:o+12],y[o+8:o+12])
                if (a['index'],vi) not in moved:self.assertEqual(x[o:o+8]+x[o+24:],y[o:o+8]+y[o+24:])
                if (a['index'],vi) not in normals:self.assertEqual(x[o+12:o+24],y[o+12:o+24])
                else:self.assertAlmostEqual(np.linalg.norm(b['vertices'][vi]['normal']),1,places=6)
            for mi,(ma,mb) in enumerate(zip(a['materials'],b['materials'])):
                self.assertEqual(ma['raw'][:132],mb['raw'][:132])
                if (a['index'],mi) not in selected:self.assertEqual(ma['strips'],mb['strips'])
        for key in ('bone_raw','texture_raw','model_descriptor_raw'):self.assertEqual(self.a[key],self.b[key])
        self.assertEqual(len(p['added_vertex_records']),48)
        self.assertEqual(len(p['adjacent_boundary_splits']),4)

    def test_real_bone_standing_walk_bend_crouch_seams_and_faces(self):
        results,poses=animation_checks(self.b,self.report['patch'])
        self.assertEqual(len(results),22);self.assertTrue(poses['standing'])
        self.assertEqual(poses['standing']['l_ninoude'],('z',70))
        for r in results.values():
            self.assertEqual(r['max_shared_position_gap'],0)
            self.assertGreater(r['minimum_skinned_normal_cosine'],0)
            self.assertGreater(r['minimum_area_ratio'],1e-6)
        self.assertEqual(self.a['bones'],self.b['bones'])

    def test_native_buffers_budget_payloads_and_exact_preview(self):
        self.assertLessEqual(len(self.fixed),148000);self.assertEqual(len(self.fixed)%2048,0)
        self.assertEqual(digest(self.fixed),self.report['pac_sha256'])
        for key,delta in [('vertices',48),('triangles',70),('meshes',0),('textures',0),('material_records',0),('bones',0)]:
            self.assertEqual(self.b['report'][key]-self.a['report'][key],delta)
        aa=dict((s['id'],r) for s,r in sections(self.base));bb=dict((s['id'],r) for s,r in sections(self.fixed))
        self.assertEqual(aa.keys(),bb.keys())
        for k in aa:
            if k!=2:self.assertEqual(aa[k],bb[k])
        with zipfile.ZipFile(self.root/'1800-PSP-hybrid-source-pelvis-restored-test-bundle.zip') as z:
            self.assertIsNone(z.testzip());self.assertEqual(z.read('preview/source-pelvis-restored.yobj'),self.raw_b)
            self.assertEqual(z.read('1800-PSP-hybrid-source-pelvis-restored.pac'),self.fixed)


if __name__=='__main__':unittest.main()
