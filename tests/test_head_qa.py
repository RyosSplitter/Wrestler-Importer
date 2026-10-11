"""Synthetic shape/winding/pose defects; no game-derived fixtures."""
import copy
import unittest

import numpy as np
import trimesh

from model_qa.geometry import Geometry
from model_qa.head import compare_head,head_mask,layout_review
from model_qa.ocular import skin
from model_qa.render import camera,raster
from model_qa.pipeline import stage_diagnosis


def skull():
    mesh=trimesh.creation.icosphere(subdivisions=1,radius=1.)
    bones=[dict(name='atama',index=0,parent=-1,rotation=[0,0,0],local_position=[0,0,0]),
           dict(name='l_mayu_00',index=1,parent=0,rotation=[0,0,0],local_position=[0,0,0])]
    weights=np.zeros((len(mesh.vertices),2));weights[:,0]=1
    return Geometry(mesh.vertices.copy(),mesh.faces.copy(),weights,['atama','l_mayu_00'],
                    ['skin']*len(mesh.faces),[[0,i] for i in range(len(mesh.vertices))],dict(bones=bones))


class HeadQATests(unittest.TestCase):
    def test_stage_trace_does_not_attribute_native_layout_to_decimation(self):
        winding=dict(region='head',pose='rest',severity='review',kind='opposed-nearby-head-face-winding')
        native=dict(winding,kind='unvalidated-small-skinned-palette')
        first,diagnosis=stage_diagnosis([winding,native],[dict(label='decimation',flags=[winding])])
        self.assertEqual(first[0]['first_flagged_supplied_stage'],'decimation')
        self.assertIsNone(first[1]['first_flagged_supplied_stage'])
        self.assertIn('runtime cause unresolved',diagnosis[0]['suspected_origin'])

    def test_identical_head_has_no_shape_or_cull_findings(self):
        g=skull();r=compare_head(g,g,resolution=96)
        self.assertEqual(r['flags'],[])
        self.assertLess(r['maximum_vertex_error_height'],1e-12)

    def test_spike_outside_original_bounds_is_not_dropped(self):
        a=skull();b=copy.deepcopy(a);b.vertices[np.argmax(b.vertices[:,1]),1]+=1.
        r=compare_head(a,b,resolution=96)
        self.assertTrue(any(f['kind']=='head-vertex-outlier' for f in r['flags']))
        self.assertGreater(r['maximum_vertex_error_height'],.4)

    def test_winding_defect_hidden_by_two_sided_renders_is_flagged(self):
        a=skull();b=copy.deepcopy(a);b.faces=b.faces[:,::-1]
        cam=camera(a.vertices,'front',96)
        np.testing.assert_array_equal(raster(a,cam)['rgb'],raster(b,cam)['rgb'])
        self.assertFalse(np.array_equal(raster(a,cam,cull='back')['rgb'],raster(b,cam,cull='back')['rgb']))
        r=compare_head(a,b,resolution=96)
        self.assertEqual(r['opposed_nearby_faces'],len(a.faces))
        self.assertTrue(any(f['kind']=='opposed-nearby-head-face-winding' for f in r['flags']))

    def test_controller_weight_defect_is_detected_after_pose(self):
        a=skull();b=copy.deepcopy(a)
        selected=b.vertices[:,1]>.5;b.weights[selected]=[0,1]
        self.assertEqual(compare_head(a,b,resolution=96)['flags'],[])
        probe=dict(frame='local',controls={'l_mayu_00':dict(translate=['x',.5])})
        pa,_=skin(a,probe);pb,_=skin(b,probe)
        r=compare_head(pa,pb,a,b,resolution=96,pose='brow-translation')
        self.assertTrue(any(f['kind']=='head-vertex-outlier' for f in r['flags']))

    def test_single_weight_native_layout_is_review_not_invalid(self):
        model=dict(bones=[dict(name='atama')],meshes=[dict(index=0,base_flag=0x17ff,
                   rigid=False,bone_palette=[0],stride=40)])
        flags=layout_review(model);self.assertEqual(flags[0]['severity'],'review')
        model['meshes'][0]['rigid']=True;self.assertEqual(layout_review(model),[])

    def test_invalid_cull_and_missing_cranial_anchor_are_refused(self):
        g=skull();cam=camera(g.vertices,'front',96)
        with self.assertRaises(ValueError):raster(g,cam,cull='unknown')
        g.model['bones'][0]['name']='root'
        with self.assertRaises(ValueError):head_mask(g)


if __name__=='__main__':unittest.main()
