"""Analytical controls for topology-independent, read-only geometric QA."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from model_qa.geometry import Geometry,Surface,align_reference,geometry,topology,posed,posed_original
from model_qa.metrics import DEFAULT_PROFILE,calibrate,detect,measure
from model_qa.pipeline import normalized_profile,run
from model_qa.regions import Region
from model_qa.render import camera,comparison,raster,save_pair


def quad(dent=0.):
    v=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0],[0,0,-dent]],dtype=float)
    f=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])
    return Geometry(v,f,np.ones((len(v),1)),['root'],['skin']*len(f),[[0,i] for i in range(len(v))],{'bones':[{'name':'root'}]})


def bones_model(points):
    names=['koshi','atama','l_te','r_te','l_ashi','r_ashi','l_kote','r_kote']
    bones=[dict(name=name,index=i,parent=-1,rotation=[0,0,0],local_position=list(p)) for i,(name,p) in enumerate(zip(names,points))]
    q=quad();vertices=[dict(position=list(p),normal=[0,0,1],weights=[1.],uv=[0,0],color=[255]*4) for p in q.vertices]
    return dict(bones=bones,bone_count=len(bones),textures=['skin'],meshes=[dict(index=0,bone_palette=[0],vertices=vertices,materials=[dict(texture_id=0,triangles=q.faces.tolist())])])


class ModelQATests(unittest.TestCase):
    def setUp(self):
        self.rois={'pelvis':Region('pelvis',np.array([-1,-1,-1.]),np.array([1,1,1.]),('front',))}

    def test_reordered_vertices_and_changed_planar_topology_have_zero_distance(self):
        source=quad();target=quad()
        order=np.array([4,2,0,3,1]);inverse=np.argsort(order)
        target.vertices=target.vertices[order];target.faces=inverse[target.faces]
        # Reference uses two large triangles; candidate has a center and four.
        source.faces=np.array([[0,1,2],[0,2,3]]);source.face_textures=['skin']*2
        r,_=measure(source,target,self.rois,source.height,count=3000)
        self.assertLess(r['overall']['maximum'],1e-12)
        self.assertEqual(detect(r,DEFAULT_PROFILE),[])

    def test_detects_local_inward_surface_without_index_correspondence(self):
        original=quad();candidate=quad(.35)
        r,_=measure(original,candidate,self.rois,original.height,count=3000)
        cam=camera(original.vertices,'front',128);a=raster(original,cam);b=raster(candidate,cam)
        depth=comparison(a,b,cam,original.height)
        r['regions']['pelvis']['views']={'front':depth}
        flags=detect(r,DEFAULT_PROFILE)
        self.assertTrue(any(f['region']=='pelvis' and f['kind']=='surface-recession-or-concavity' for f in flags))
        self.assertGreater(depth['inward_depth_p95_height'],.1)
        self.assertLess(depth['projected_depth_volume_proxy'],0)
        self.assertEqual(depth['silhouette_iou'],1.)

    def test_camera_is_fixed_to_source_even_when_candidate_is_shifted(self):
        a=quad();b=quad();b.vertices[:,0]+=.2
        cam=camera(a.vertices,'front',128)
        r=comparison(raster(a,cam),raster(b,cam),cam,a.height)
        self.assertLess(r['silhouette_iou'],.9)
        self.assertGreater(r['edge_distance_p95_height'],.05)
        np.testing.assert_array_equal(raster(a,cam)['rgb'],raster(a,cam)['rgb'])

    def test_uniform_alignment_preserves_distortion_instead_of_hiding_it(self):
        points=np.array([[0,0,0],[0,3,0],[3,2,0],[-3,2,0],[1,-3,0],[-1,-3,0],[2,2,.5],[-2,2,.5]],dtype=float)
        source=bones_model(points);target=bones_model(points*1.7+[2,4,1])
        for v in target['meshes'][0]['vertices']:v['position']=(np.array(v['position'])*1.7+[2,4,1]).tolist()
        aligned,report=align_reference(source,target)
        np.testing.assert_allclose(geometry(aligned).vertices,geometry(target).vertices,atol=1e-12)
        self.assertFalse(report['nonuniform_scaling']);self.assertAlmostEqual(report['scale'],1.7)
        stretched=bones_model(points*np.array([1.7,1.2,.8]))
        _,fit=align_reference(source,stretched)
        self.assertGreater(max(fit['landmark_errors']),.5)

    def test_topology_reports_open_volume_and_relative_degenerate_faces(self):
        a=quad();self.assertIsNone(topology(a,a.height)['closed_volume'])
        a.faces=np.vstack((a.faces,[0,0,1]))
        self.assertEqual(topology(a,a.height)['degenerate_triangles'],1)
        s=Surface(a,a.height)
        self.assertEqual(len(s.valid_ids),4)

    def test_original_rig_motion_uses_aligned_target_axes(self):
        points=np.array([[0,0,0],[0,3,0],[3,2,0],[-3,2,0],[1,-3,0],[-1,-3,0],[2,2,.5],[-2,2,.5]],dtype=float)
        angle=.4;r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        source=bones_model(points);target=bones_model(1.7*points@r.T+[2,4,1])
        for a,b in zip(source['meshes'][0]['vertices'],target['meshes'][0]['vertices']):b['position']=(1.7*r@a['position']+[2,4,1]).tolist()
        _,alignment=align_reference(source,target);controls={'koshi':('x',30)}
        expected=posed(geometry(target),controls)
        actual=posed_original(source,alignment,controls)
        np.testing.assert_allclose(actual.vertices,expected.vertices,atol=1e-12)

    def test_optional_numeric_depth_storage_preserves_metrics_and_uses_float32(self):
        a,b=quad(),quad(.35);cam=camera(a.vertices,'front',128)
        with tempfile.TemporaryDirectory() as folder:
            first,_=save_pair(folder,'plain',a,b,cam,2.)
            self.assertFalse((Path(folder)/'plain-depth.npz').exists())
            second,_=save_pair(folder,'stored',a,b,cam,2.,save_depth=True)
            self.assertEqual(first,second)
            with np.load(Path(folder)/'stored-depth.npz') as z:self.assertEqual(z['source'].dtype,np.float32)

    def test_animation_flag_requires_extra_error_beyond_rest(self):
        r,_=measure(quad(),quad(),self.rois,2.,count=3000)
        p=copy.deepcopy(r);p['regions']['pelvis']['distance']['p95_height']=.004
        f=detect(p,DEFAULT_PROFILE,'jaw-open',r)
        self.assertTrue(any(x['kind']=='pose-dependent-deformation' for x in f))
        self.assertEqual(detect(p,DEFAULT_PROFILE,'jaw-open',p),[])

    def test_calibration_uses_only_explicit_trusted_regions_and_keeps_floors(self):
        r,_=measure(quad(),quad(),self.rois,2.,count=3000)
        report={'inputs':{'candidate':'control'},'rest':r}
        p=calibrate([('trusted conversion',report,['pelvis'])])
        self.assertEqual(set(p['regional']),{'pelvis'})
        self.assertEqual(p['regional']['pelvis']['distance_p95_height'],DEFAULT_PROFILE['distance_p95_height'])
        self.assertEqual(p['animation_extra_p95_height'],DEFAULT_PROFILE['animation_extra_p95_height'])

    def test_invalid_tolerance_and_existing_output_are_refused(self):
        with self.assertRaises(ValueError):normalized_profile({'distance_p95_height':-1})
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'keep.pac';marker.write_bytes(b'previously validated')
            with self.assertRaises(FileExistsError):run('missing-source.pac','missing-candidate.pac',folder)
            self.assertEqual(marker.read_bytes(),b'previously validated')


if __name__=='__main__':unittest.main()
