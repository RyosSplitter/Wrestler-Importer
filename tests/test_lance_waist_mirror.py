"""Independent delivery checks for the mirrored waistband topology repair."""
import json
from pathlib import Path
import unittest

import numpy as np

from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.weight_trial_review import POSES, deform


class LanceWaistMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]/'downloads'
        cls.base=(root/'1800-PSP-hybrid-waist-abs-fix.pac').read_bytes()
        cls.fixed=(root/'1800-PSP-hybrid-mirrored-left-waist.pac').read_bytes()
        cls.report=json.loads((root/'1800-PSP-hybrid-mirrored-left-waist-report.json').read_text())
        cls.a=audit_yobj(next(raw for s,raw in sections(cls.base) if s['id']==2))
        cls.b=audit_yobj(next(raw for s,raw in sections(cls.fixed) if s['id']==2))

    def test_left_waist_contour_matches_right_reflection(self):
        plane=self.report['patch']['reflection_plane'];axis=np.array(plane['normal']);center=np.array(plane['point'])
        added=self.report['patch']['added_vertex_records'];p=next(r['vertex'] for r in added if r['mesh']==53)
        for left,right in [(p,6),(23,5),(21,7),(22,17),(24,4)]:
            v=self.a['meshes'][53]['vertices'][right];point=np.array(v['position'])
            mirror=point-2*np.dot(point-center,axis)*axis
            # New/moved points are exact float32 reflections. Retained source
            # anchors have tiny pre-existing bilateral differences (<0.00015
            # model units), which this local repair deliberately preserves.
            tolerance=5e-7 if left in (p,23) else 1.5e-4
            np.testing.assert_allclose(self.b['meshes'][53]['vertices'][left]['position'],mirror,rtol=0,atol=tolerance)
            normal=np.array(v['normal']);normal-=2*np.dot(normal,axis)*axis;normal/=np.linalg.norm(normal)
            np.testing.assert_allclose(self.b['meshes'][53]['vertices'][left]['normal'],normal,rtol=0,atol=1e-7)
        expected={(21,p,23),(p,22,23),(21,8,p),(8,6,p),(23,22,24)}
        self.assertTrue(expected<=set(self.b['meshes'][53]['materials'][0]['triangles']))

    def test_original_weight_bits_and_all_undeclared_vertex_fields_preserved(self):
        normals={(v['mesh'],v['vertex']) for v in self.report['patch']['mirrored_normal_records']}
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            self.assertEqual(a['opaque'],b['opaque'])
            for vi in range(len(a['vertices'])):
                raw_a=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']]
                raw_b=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']]
                offset=4*a['weight_slots'];self.assertEqual(raw_a[:offset],raw_b[:offset])
                self.assertEqual(raw_a[offset+8:offset+12],raw_b[offset+8:offset+12])
                if (a['index'],vi)==(53,23):continue
                self.assertEqual(raw_a[offset:offset+12],raw_b[offset:offset+12])
                self.assertEqual(raw_a[offset+24:],raw_b[offset+24:])
                if (a['index'],vi) not in normals:self.assertEqual(raw_a,raw_b)
        self.assertEqual(self.a['bone_raw'],self.b['bone_raw'])
        self.assertEqual(self.a['texture_raw'],self.b['texture_raw'])
        self.assertEqual(self.a['model_descriptor_raw'],self.b['model_descriptor_raw'])

    def test_size_counts_textures_and_render_state(self):
        self.assertEqual(len(self.fixed),136*1024)
        for key,delta in [('vertices',2),('triangles',2),('indices',6),('strips',2),('meshes',0),('textures',0),('material_records',0),('bones',0)]:
            self.assertEqual(self.b['report'][key]-self.a['report'][key],delta)
        old=dict((s['id'],raw) for s,raw in sections(self.base));new=dict((s['id'],raw) for s,raw in sections(self.fixed))
        self.assertEqual(old.keys(),new.keys())
        for key in old:
            if key!=2:self.assertEqual(old[key],new[key])
        for a,b in zip(self.a['meshes'],self.b['meshes']):
            for ma,mb in zip(a['materials'],b['materials']):self.assertEqual(ma['raw'][:132],mb['raw'][:132])

    def test_new_vertex_skinning_mirrors_right_and_seam_stays_closed(self):
        model=self.b;positions=np.array([v['position'] for m in model['meshes'] for v in m['vertices']])
        weights=np.zeros((len(positions),len(model['bones'])));row=0;rows=[]
        keys={(v['mesh'],v['vertex']) for v in self.report['patch']['added_vertex_records']}
        names={b['name']:b['index'] for b in model['bones']}
        donor=self.a['meshes'][53];src=donor['vertices'][6];expected=np.zeros(len(model['bones']))
        for bone,w in zip(donor['bone_palette'],src['weights']):
            name=model['bones'][bone]['name'];name=('l_'+name[2:]) if name.startswith('r_') else ('r_'+name[2:]) if name.startswith('l_') else name
            expected[names[name]]=w
        for mesh in model['meshes']:
            for vi,v in enumerate(mesh['vertices']):
                for b,w in zip(mesh['bone_palette'],v['weights']):weights[row,b]=w
                if (mesh['index'],vi) in keys:rows.append(row)
                row+=1
        self.assertEqual(len(rows),2)
        for row in rows:np.testing.assert_array_equal(weights[row],expected)
        for name,pose in POSES.items():
            result=deform(dict(bones=model['bones'],bone_count=len(model['bones'])),positions,weights,pose)
            np.testing.assert_array_equal(result[rows[0]],result[rows[1]],err_msg=name)


if __name__=='__main__':unittest.main()
