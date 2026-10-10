"""Known pad defect plus topology-independent material/seam controls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np

from model_qa.geometry import Geometry,geometry,posed
from model_qa.material_boundaries import measure,detect
from model_qa.metrics import DEFAULT_PROFILE,detect as detect_all
from model_qa.pipeline import normalized_profile,POSES,run,render_material_flags
from tools.psp_mesh_merge_trial import sections
from tools.psp_mesh_audit import audit_yobj


def square(split=False):
    vertices=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],dtype=float)
    if split:
        vertices=np.vstack((vertices,[.5,0,0],[.5,1,0]))
        faces=np.array([[0,4,5],[0,5,3],[4,1,2],[4,2,5]])
    else:faces=np.array([[0,1,2],[0,2,3]])
    return Geometry(vertices,faces,np.ones((len(vertices),1)),['root'],['pad']*len(faces),
        [[0,i] for i in range(len(vertices))],{})


class MaterialBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        with zipfile.ZipFile(root/'downloads/Jericho-SVR2011-PSP-elbow-pad-TEST-bundle.zip') as z:
            cls.source=json.loads(z.read('trial/source-aligned-weighted.json'))
        def native(label):
            pac=(root/'downloads'/('Jericho-SVR2011-PSP-'+label+'-TEST.pac')).read_bytes()
            return audit_yobj(next(r for s,r in sections(pac) if s['id']==2))
        cls.bad=native('eye-compatibility');cls.good=native('elbow-pad')

    def test_known_pad_point_flags_before_and_passes_after(self):
        reference=geometry(self.source)
        for model,expected in ((self.bad,True),(self.good,False)):
            result=measure(reference,geometry(model),reference.height)
            flags=detect(result,DEFAULT_PROFILE,height=reference.height)
            self.assertEqual(any(f['texture']=='y2j_hiji' for f in flags),expected)
            if expected:self.assertGreater(result['materials']['y2j_hiji']['maximum_height'],.02)
            else:self.assertEqual(result['materials']['y2j_hiji']['maximum_height'],0)

    def test_elbow_motion_and_shared_skin_seams_are_checked(self):
        ref,new=geometry(self.source),geometry(self.good)
        rest=measure(ref,new,ref.height)
        for name in ('standing','elbow-flex-left','elbow-flex-right','shoulders-up'):
            controls=POSES[name]
            r=measure(posed(ref,controls),posed(new,controls),ref.height,ref,new)
            self.assertFalse(any(f['texture']=='y2j_hiji' for f in detect(r,DEFAULT_PROFILE,name,rest,ref.height)))
            pad=r['materials']['y2j_hiji']
            self.assertEqual(pad['candidate_shared_seam_groups'],21)
            self.assertEqual(pad['candidate_seam_gap'],0)

    def test_boundary_subdivision_and_reordering_are_not_defects(self):
        a,b=square(),square(True)
        order=np.arange(len(b.vertices))[::-1];inverse=np.argsort(order)
        b.vertices=b.vertices[order];b.faces=inverse[b.faces]
        r=measure(a,b,1.)
        self.assertEqual(r['materials']['pad']['maximum_height'],0)
        self.assertEqual(detect(r,{}),[])

    def test_peak_corner_is_detected_even_with_high_percentile_limit(self):
        a,b=square(),square();b.vertices=b.vertices.copy();b.vertices[2,0]+=.1
        r=measure(a,b,1.)
        flags=detect(r,{'material_boundaries':{'p95_height':1.,'maximum_height':.003}})
        self.assertEqual(len(flags),1)
        self.assertTrue(any(e['metric']=='maximum_height' for e in flags[0]['evidence']))

    def test_posed_shared_alias_gap_flags_without_rest_geometry_drift(self):
        g=square();g.vertices=np.vstack((g.vertices,g.vertices))
        g.faces=np.vstack((g.faces,g.faces+4));g.face_textures=['pad','pad','skin','skin']
        old=copy.deepcopy(g);current=copy.deepcopy(g);current.vertices[4:,2]+=.01
        rest=measure(g,old,1.)
        result=measure(g,current,1.,g,old)
        flags=detect(result,{},'elbow-flex',rest,1.)
        self.assertTrue(any(e['metric']=='seam_extra_height' for f in flags for e in f['evidence']))

    def test_invalid_boundary_tolerances_are_refused(self):
        with self.assertRaises(ValueError):normalized_profile({'material_boundaries':{'maximum_height':-1}})
        with self.assertRaises(ValueError):normalized_profile({'material_boundaries':{'per_texture':{'pad':{'seam_extra_height':0}}}})

    def test_unmatched_material_is_reported_for_review(self):
        a,b=square(),square();b.face_textures=['renamed']*2
        flags=detect(measure(a,b,1.),{})
        self.assertEqual({f['texture'] for f in flags},{'pad','renamed'})
        self.assertTrue(all(f['coverage_status']=='unmatched-material' for f in flags))

    def test_default_pipeline_includes_boundary_findings_and_html(self):
        # Use actual aligned source stage and native defect; no converter invoked.
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);source=path/'source.json';source.write_text(json.dumps(self.source))
            result=run(source,root/'downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST.pac',path/'qa',
                samples=2000,resolution=96,animations=False,renders=False)
            self.assertIn('material_boundaries',result['rest'])
            self.assertTrue(any(f.get('texture')=='y2j_hiji' for f in result['unresolved_review']))
            self.assertIn('Material and accessory boundaries',(path/'qa/report.html').read_text())
            self.assertTrue(result['inputs_unchanged']);self.assertFalse(result['can_replace_best_model'])

    def test_flagged_pad_generates_matching_front_back_side_closeups(self):
        source,candidate=geometry(self.source),geometry(self.bad)
        metrics={'material_boundaries':measure(source,candidate,source.height)}
        flags=[f for f in detect(metrics['material_boundaries'],{},height=source.height) if f['texture']=='y2j_hiji']
        with tempfile.TemporaryDirectory() as folder:
            gallery=render_material_flags(source,candidate,metrics,flags,folder,source.height,96)
            self.assertEqual({r['view'] for r in gallery},{'front','back','left','right'})
            for r in gallery:
                self.assertTrue((Path(folder)/Path(r['file']).name).is_file())
                self.assertEqual(r['region'],'material:y2j_hiji')


if __name__=='__main__':unittest.main()
