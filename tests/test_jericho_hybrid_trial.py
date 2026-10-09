"""Validate the delivered Jericho candidate, including the PAC/preview identity."""
from collections import Counter
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import numpy as np
from PIL import Image

from tools.jericho_hybrid_trial import pose_checks
from tools.lance_anatomy_restore import oriented_face_key
from tools.lance_rear_waist_fix import posed_view
from tools.pac_inspect import inspect_pac, parse_textures
from tools.psp_mesh_audit import audit_yobj, digest
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.texture_convert import read_gim


class JerichoTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.pac=(cls.root/'downloads/0600-PSP-hybrid-Jericho.pac').read_bytes()
        cls.report=json.loads((cls.root/'downloads/0600-PSP-hybrid-Jericho-report.json').read_text())
        cls.payloads={s['id']:r for s,r in sections(cls.pac)}
        cls.model=audit_yobj(cls.payloads[2])
        cls.bundle=cls.root/'downloads/0600-PSP-hybrid-Jericho-test-bundle.zip'

    def test_native_buffers_budget_and_unchanged_psp_base(self):
        self.assertLessEqual(len(self.pac),148000)
        self.assertEqual(len(self.pac)%2048,0)
        self.assertEqual(digest(self.pac),self.report['pac_sha256'])
        base={s['id']:r for s,r in sections((self.root/'assets/Kurt-Angle-Ring.PAC').read_bytes())}
        self.assertEqual(self.payloads.keys(),base.keys())
        for sid in base:
            if sid not in (2,9):self.assertEqual(self.payloads[sid],base[sid])
        self.assertEqual(self.model['bone_raw'],audit_yobj(base[2])['bone_raw'])
        for s in inspect_pac(self.pac)['sections']:self.assertEqual(s['offset']%16,0)
        for key in ('vertices','triangles','meshes','textures','bones','material_records'):
            self.assertEqual(self.model['report'][key],self.report['output'][key])
        for m in self.model['meshes']:
            for v in m['vertices']:
                self.assertAlmostEqual(sum(v['weights']),1,places=6)
                self.assertAlmostEqual(np.linalg.norm(v['normal']),1,places=5)

    def test_preserved_source_surfaces_and_uv_signatures(self):
        for name,r in self.report['protected_source_surfaces'].items():
            tid=self.model['texture_names'].index(name)
            faces=Counter(oriented_face_key(m,t) for m in self.model['meshes'] for a in m['materials'] if a['texture_id']==tid for t in a['triangles'])
            self.assertEqual(sum(faces.values()),r['triangles'])
            self.assertEqual(digest(b''.join(b''.join(t) for t in sorted(faces.elements()))),r['oriented_source_surface_sha256'])
            uvs=Counter(min(tuple(c[i:]+c[:i]) for i in range(3)) for m in self.model['meshes'] for a in m['materials'] if a['texture_id']==tid for t in a['triangles'] for c in [[struct.pack('<3f2f',*m['vertices'][v]['position'],*m['vertices'][v]['uv']) for v in t]])
            self.assertEqual(digest(b''.join(b''.join(t) for t in sorted(uvs.elements()))),r['oriented_position_uv_sha256'])
            self.assertLess(r['maximum_hybrid_weight_difference'],2e-6)
        self.assertEqual(self.report['protected_source_surfaces']['y2j_body']['triangles'],391)
        self.assertEqual(self.report['protected_source_surfaces']['y2j_mata']['triangles'],278)

    def test_synthetic_standing_walk_bend_and_crouch(self):
        results=pose_checks(self.model,self.report['pose_definitions'])
        self.assertEqual(results,self.report['pose_validation'])
        self.assertEqual(len(results),23)
        for row in results.values():
            self.assertEqual(row['maximum_coincident_position_gap'],0)
            self.assertGreater(row['minimum_protected_body_face_area_ratio'],1e-6)

    def test_actual_texture_payloads_pngs_and_native_cutout_flags(self):
        table=self.payloads[9];textures={e['name']:e for e in parse_textures(table)}
        self.assertEqual(set(textures),set(self.model['texture_names']))
        with zipfile.ZipFile(self.bundle) as z:
            for info in self.report['textures']:
                entry=textures[info['name']]
                self.assertEqual(self.model['texture_names'][info['index']],info['name'])
                raw=table[entry['offset']:entry['offset']+entry['size']]
                self.assertEqual(raw,z.read('preview/'+info['name']+'.gim'))
                ix,palette=read_gim(raw);rgba=palette[ix]
                self.assertEqual(digest(rgba.tobytes()),info['converted_rgba_sha256'])
                with z.open('preview/'+info['name']+'.png') as f:
                    np.testing.assert_array_equal(np.asarray(Image.open(f)),rgba)
                if info['cutout_palette_and_pixels_exact']:
                    self.assertEqual(info['source_rgba_sha256'],info['converted_rgba_sha256'])
                    self.assertEqual(info['name'],'y2j_hair')
            for m in self.model['meshes']:
                for a in m['materials']:
                    info=self.report['textures'][a['texture_id']]
                    expected=(7 if info['bits']==8 else 5)|(0x110 if info['cutout_palette_and_pixels_exact'] else 0)
                    self.assertEqual(a['control'],expected)

    def test_final_pac_preview_and_screenshot_inputs_are_identical(self):
        with zipfile.ZipFile(self.bundle) as z, tempfile.TemporaryDirectory() as td:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read('0600-PSP-hybrid-Jericho.pac'),self.pac)
            self.assertEqual(z.read('preview/prepared.yobj'),self.payloads[2])
            path=Path(td)/'view.obj'
            write_preview(self.model,path)
            self.assertEqual(path.read_bytes(),z.read('preview/prepared.obj'))
            for view,angle in [('front',0),('rear',180),('side',90)]:
                write_preview(posed_view(self.model,{},angle),path)
                self.assertEqual(path.read_bytes(),z.read('preview/jericho-'+view+'.obj'))
            for name in ('standing','forward-bend','crouch'):
                write_preview(posed_view(self.model,self.report['pose_definitions'][name],135),path)
                self.assertEqual(path.read_bytes(),z.read('preview/jericho-'+name+'.obj'))
            manifest=json.loads(z.read('manifest.json'))
            for name,sha in manifest['sha256'].items():self.assertEqual(digest(z.read(name)),sha)
            for shot in self.report['noesis_screenshots']:
                self.assertEqual(digest(z.read(shot['image'])),shot['image_sha256'])
                self.assertEqual(digest(z.read(shot['obj'])),shot['obj_sha256'])


if __name__=='__main__':unittest.main()
