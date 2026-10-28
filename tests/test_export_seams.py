"""Source-linked local seam regressions, including same-texture UV islands."""
import copy
import json
import unittest
import tempfile
from pathlib import Path

from model_qa.geometry import geometry
from model_qa.export_seams import prepare,measure,summary,inventory
from desktop.seam_review import save_warning,seam_status


def suit(gap=0.,split=False):
    bones=[dict(name='root',index=0,parent=-1,local_position=[0,0,0],rotation=[0,0,0])]
    meshes=[]
    for index in range(2):
        left,right=(-1,0) if index==0 else (gap,1)
        points=[[left,0,0],[right,0,0],[right,-1,0],[left,-1,0]]
        u0,u1=(0,.4) if index==0 else (.6,1.)
        uvs=[[u0,0],[u1,0],[u1,1],[u0,1]]
        tris=[[0,1,2],[0,2,3]]
        if split:
            points += [[left,-.5,0],[right,-.5,0]]
            uvs += [[u0,.5],[u1,.5]]
            tris=[[0,1,5],[0,5,4],[4,5,2],[4,2,3]]
        meshes.append(dict(index=index,bone_palette=[0],
            vertices=[dict(position=p,uv=uv,normal=[0,0,1],weights=[1.],color=[255]*4) for p,uv in zip(points,uvs)],
            materials=[dict(texture_id=0,triangles=tris)]))
    return dict(bones=bones,textures=['gear'],meshes=meshes)


class ExportSeamTests(unittest.TestCase):
    def audit(self,a,b):
        a,b=geometry(a),geometry(b)
        plan=prepare(a,b,1.)
        return plan,a,b,measure(plan,a,b)

    def test_same_texture_uv_seam_is_measured_and_unchanged_passes(self):
        plan,a,b,r=self.audit(suit(),suit())
        self.assertEqual(r['matched_contact_locations'],2)
        self.assertEqual(r['flags'],[])
        self.assertEqual(len(inventory(a,1.)['edges']['gear']),8)

    def test_small_already_open_export_is_not_hidden_by_coincidence_grouping(self):
        plan,a,b,r=self.audit(suit(),suit(.001))
        self.assertGreater(r['maximum_extra_gap_height'],.0009)
        self.assertTrue(any(f['kind']=='export-seam-local-opening' for f in r['flags']))

    def test_source_gap_elsewhere_cannot_excuse_new_local_pose_gap(self):
        plan,a,b,_=self.audit(suit(),suit())
        a.vertices[4,2]=.1;b.vertices[4,2]=.1
        b.vertices[7,2]=.001
        r=measure(plan,a,b,'wrist-flex')
        self.assertEqual(r['flagged_pairs'],1)
        self.assertAlmostEqual(r['maximum_extra_gap_height'],.001)

    def test_source_authorized_motion_is_not_a_new_opening(self):
        plan,a,b,_=self.audit(suit(),suit())
        a.vertices[4:,2]+=.02;b.vertices[4:,2]+=.02
        r=measure(plan,a,b,'crouch')
        self.assertEqual(r['flagged_pairs'],0)
        self.assertEqual(r['maximum_extra_gap_height'],0)

    def test_subdivision_and_record_reordering_do_not_create_findings(self):
        other=suit(split=True)
        for mesh in other['meshes']:
            mesh['vertices'].reverse();n=len(mesh['vertices'])
            for mat in mesh['materials']:mat['triangles']=[[n-1-i for i in t] for t in mat['triangles']]
        _,_,_,r=self.audit(suit(),other)
        self.assertEqual(r['flags'],[])

    def test_missing_side_is_reported_as_unmeasured(self):
        other=suit();other['meshes']=other['meshes'][:1]
        _,_,_,r=self.audit(suit(),other)
        self.assertTrue(r['unmatched_sides'])
        self.assertTrue(any(f['kind']=='export-seam-unmeasured-coverage' for f in r['flags']))

    def test_displaced_edge_interior_is_detected(self):
        other=suit(split=True)
        other['meshes'][1]['vertices'][4]['position'][2]=.025
        _,_,_,r=self.audit(suit(),other)
        self.assertGreater(r['networks']['gear']['maximum_height'],.01)
        self.assertTrue(any(f['kind']=='export-seam-edge-drift' for f in r['flags']))

    def test_native_palette_split_without_uv_change_is_virtually_joined(self):
        model=suit();model['meshes'][1]['vertices'][0]['uv']=[.4,0]
        model['meshes'][1]['vertices'][3]['uv']=[.4,1]
        self.assertEqual(len(inventory(geometry(model),1.)['edges']['gear']),6)

    def test_read_only_serializable_report_and_save_wording(self):
        a,b=suit(),suit(.001);before=copy.deepcopy((a,b))
        _,_,_,r=self.audit(a,b)
        report=summary(r,{})
        json.dumps(report,allow_nan=False)
        self.assertEqual((a,b),before)
        result=dict(review_flags=report['review_findings'],export_seams=report)
        self.assertIn('Seams:',save_warning(result))
        self.assertIn('unmatched/ambiguous',seam_status(result))
        self.assertEqual(seam_status({}),'')

    def test_invalid_geometry_scale_and_nonfinite_uv_are_rejected(self):
        g=geometry(suit())
        for height in (0,-1,float('nan')):
            with self.assertRaises(ValueError):prepare(g,g,height)
        g.model['meshes'][0]['vertices'][0]['uv'][0]=float('nan')
        with self.assertRaises(ValueError):inventory(g,1.)

    def test_located_findings_have_bounded_source_framed_closeups(self):
        from model_qa.pipeline import render_seam_flags,seam_html
        plan,a,b,r=self.audit(suit(),suit(.001))
        with tempfile.TemporaryDirectory() as folder:
            gallery=render_seam_flags(a,b,r['flags'],folder,1.,96,limit=1)
            self.assertEqual(len(gallery),4)
            self.assertEqual({r['view'] for r in gallery},{'front','back','left','right'})
            self.assertTrue(all((Path(folder)/Path(row['file']).name).is_file() for row in gallery))
        text=seam_html(summary(r,{}))
        self.assertIn('Worst local openings',text)
        self.assertIn('gear',text)


if __name__=='__main__':unittest.main()
