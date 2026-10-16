"""Opt-in face research contracts, generated fixture and two native references."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from model_creator.experiments.facial import (Contour,partition,records,fan,point_key,
    stitch_contours,serialize,source_signature,graft_rig,pose_review,topology_review,winding_review,regularized_partition)
from model_creator.core import load_source
from model_creator.native import audit_yobj
from tools.prepare_model import bone_matrices


def synthetic_head():
    """Original asset-free octagonal head: one nose fan, one posterior fan."""
    bones=[]
    for name,parent,pos in (('atama',-1,(0,-8,0)),('l_eye',0,(.3,-1,-.9)),
                            ('r_eye',0,(-.3,-1,-.9)),('d_kuchi',0,(0,-.4,-.2))):
        bones.append(dict(index=len(bones),name=name,parent=parent,local_position=pos,rotation=(0,0,0)))
    points=[(0,-9,-1.4),(0,-9,.9)]+[(.9*np.cos(a),-9+np.sin(a),-.3) for a in np.arange(8)*np.pi/4]
    vertices=[dict(position=list(p),normal=[0,0,-1],uv=[i/10,.25],color=[255]*4,weights=[1.,0.]) for i,p in enumerate(points)]
    faces=[[0,2+i,2+(i+1)%8] for i in range(8)]+[[1,2+(i+1)%8,2+i] for i in range(8)]
    return dict(bones=bones,texture_names=['generated_face'],meshes=[dict(index=0,vertices=vertices,
        bone_palette=[0,3],materials=[dict(texture_id=0,triangles=faces)])])


class FacialTopologyTests(unittest.TestCase):
    def test_generated_fixture_extracts_real_edges_and_preserves_partition(self):
        m=synthetic_head();original=copy.deepcopy(m);p=partition(m)
        self.assertEqual(len(p.face),8);self.assertEqual(len(p.contour),8)
        self.assertEqual(p.report['shell_boundary_edges_verified'],8)
        self.assertEqual(p.report,partition(m).report);self.assertEqual(m,original)

    def test_missing_landmarks_and_materials_require_profile(self):
        m=synthetic_head();m['bones'][1]['name']='unknown'
        with self.assertRaisesRegex(ValueError,'landmarks'):partition(m)
        m=synthetic_head();m['texture_names']=['unclassified']
        with self.assertRaisesRegex(ValueError,'profile'):partition(m)

    def test_unpaired_shell_edge_rejected(self):
        m=synthetic_head();m['meshes'][0]['materials'][0]['triangles'].pop()
        with self.assertRaisesRegex(ValueError,'not paired'):partition(m)

    def test_regularization_changes_ownership_only(self):
        m=synthetic_head();original=copy.deepcopy(m);p=regularized_partition(m)
        self.assertEqual(p.face,partition(m).face);self.assertEqual(m,original)
        native=load_source('creator_library/pacs/Chris-Masters.PAC',library=True)['model']
        before=partition(native,-.9);after=regularized_partition(native,-.9)
        removed={tuple(k) for k in after.report['outer_ear_triangles_retained_in_shell']}
        self.assertEqual(before.face-after.face,removed);self.assertEqual(len(removed),2)

    def test_folded_attachment_parameterization_rejected(self):
        m=synthetic_head();p=partition(m);p.contour[1],p.contour[4]=p.contour[4],p.contour[1]
        with self.assertRaisesRegex(ValueError,'folds'):Contour(p,records(m,0,[b['name'] for b in m['bones']],lambda k:k in p.face))

    def test_nonmanifold_face_rejected(self):
        m=synthetic_head();m['meshes'][0]['materials'][0]['triangles']+=[[0,2,3],[0,3,4]]
        with self.assertRaisesRegex(ValueError,'ambiguous'):partition(m)

    def test_coincident_attribute_records_are_not_welded(self):
        m=synthetic_head();mesh=m['meshes'][0];v=copy.deepcopy(mesh['vertices'][2]);v['uv']=[.87,.91];v['weights']=[.6,.4]
        mesh['vertices'].append(v);mesh['materials'][0]['triangles'][0][1]=len(mesh['vertices'])-1
        p=partition(m);rows=records(m,0,['atama','l_eye','r_eye','d_kuchi'],lambda k:k in p.face)
        equal=[v for r in rows for v in r['poly'] if point_key(v['p'])==point_key(mesh['vertices'][2]['position'])]
        self.assertEqual(len({v['origin'] for v in equal}),2)
        self.assertEqual(len({tuple(v['w']) for v in equal}),2)
        with self.assertRaisesRegex(ValueError,'incompatible source weights'):Contour(p,rows)

    def test_collinear_boundary_sample_is_kept_in_cap_triangulation(self):
        points=[(0,0,0),(1,0,0),(2,0,0),(2,1,0)]
        poly=[dict(p=np.array(v,float),boundary=True) for v in points]
        result=fan(poly);self.assertEqual(len(result),2)
        edges={tuple(sorted((point_key(a['p']),point_key(b['p'])))) for tri in result for a,b in zip(tri,tri[1:]+tri[:1])}
        for a,b in zip(poly,poly[1:]+poly[:1]):self.assertIn(tuple(sorted((point_key(a['p']),point_key(b['p'])))),edges)

    def test_collapsed_polygon_rejected(self):
        with self.assertRaisesRegex(ValueError,'Collapsed'):
            fan([dict(p=np.array((x,0,0),float),boundary=True) for x in range(4)])

    def test_ring_fit_does_not_change_interior_or_uvs(self):
        a=synthetic_head();b=copy.deepcopy(a);b['meshes'][0]['vertices'][0]['position'][2]=-.9
        names=[b['name'] for b in a['bones']];pa,pb=partition(a),partition(b)
        sh=records(a,0,names,lambda k:k not in pa.face);ins=records(b,1,names,lambda k:k in pb.face)
        old=[(v['origin'],v['p'].copy(),v['uv'].copy()) for r in ins for v in r['poly'] if v['origin'][2]==0]
        stitch_contours(sh,ins,pa,pb,np.zeros(3))
        new=[v for r in ins for v in r['poly'] if v['origin'] is not None and v['origin'][2]==0]
        for (_,p,uv),v in zip(old,new):np.testing.assert_array_equal(p,v['p']);np.testing.assert_array_equal(uv,v['uv'])


class NativeFacialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=[load_source('creator_library/pacs/'+p,library=True) for p in ('Batista.PAC','Chris-Masters.PAC')]
        a,b=[s['model'] for s in cls.sources];names=[b['name'] for b in a['bones']]
        cls.parts=[regularized_partition(a,-1),regularized_partition(b,-.9)]
        eye=lambda m:np.mean([bone_matrices(m)[b['index'],:3,3] for b in m['bones'] if b['name'] in ('l_eye','r_eye')],axis=0)
        cls.translation=eye(a)-eye(b);pa,pb=cls.parts
        cls.shell=records(a,0,names,lambda k:k not in pa.face|pa.attachments)
        cls.insert=records(b,1,names,lambda k:k in pb.face|pb.attachments,cls.translation)
        cls.seam=stitch_contours(cls.shell,cls.insert,pa,pb,cls.translation)
        cls.base,cls.rig=graft_rig(a,b,cls.shell,cls.insert,cls.translation)
        cls.raw,cls.textures,cls.origins,_=serialize(cls.base,cls.sources,cls.shell+cls.insert)
        cls.output=audit_yobj(cls.raw)

    def test_same_face_reconstruction_is_attributes_not_binary_shortcut(self):
        source=self.sources[0];m=source['model'];names=[b['name'] for b in m['bones']];p=self.parts[0]
        a=records(m,0,names,lambda k:k not in p.face|p.attachments);b=records(m,0,names,lambda k:k in p.face|p.attachments)
        raw,t,_,_=serialize(m,[source],sorted(a+b,key=lambda r:(r['mesh'],r['material'],r['triangle'])))
        result=audit_yobj(raw)
        self.assertNotEqual(raw,source['sections'][2]);self.assertEqual(result['bone_raw'],m['bone_raw'])
        self.assertEqual(source_signature(m,source['textures']),source_signature(result,{k.casefold():v for k,v in t.items()}))

    def test_native_serialization_is_deterministic(self):
        raw,textures,_,_=serialize(self.base,self.sources,self.shell+self.insert)
        self.assertEqual(raw,self.raw);self.assertEqual(textures,self.textures)

    def test_unsupported_second_descriptor_is_not_silently_dropped(self):
        sources=copy.deepcopy(self.sources);sources[1]['model']['descriptors']*=2
        with self.assertRaisesRegex(ValueError,'one descriptor per donor'):
            serialize(self.base,sources,self.shell+self.insert)

    def test_different_opaque_strip_metadata_is_not_silently_replaced(self):
        sources=copy.deepcopy(self.sources)
        material=sources[0]['model']['meshes'][self.shell[0]['mesh']]['materials'][self.shell[0]['material']]
        header=bytearray(material['strip_headers'][0]);header[0]^=1
        material['strip_headers'].append(bytes(header))
        with self.assertRaisesRegex(ValueError,'opaque strip metadata'):
            serialize(self.base,sources,self.shell+self.insert)

    def test_graft_preserves_native_animation_rotation_records(self):
        a,b=[s['model'] for s in self.sources]
        from tools.weight_trial_review import descendant_names
        expressions=descendant_names(b,'atama')-{'atama'}
        for bone in self.output['bones']:
            name=bone['name'];native=next(x for x in (b if name in expressions else a)['bones'] if x['name']==name)
            # These native references share rotation records. No equivalent
            # Euler re-decomposition is allowed to replace the local axes.
            self.assertEqual(bone['rotation'],native['rotation'])

    def test_actual_native_join_and_donor_core_pass_both_axis_conventions(self):
        topology=topology_review(self.output,self.seam['seam_points']);self.assertTrue(topology['passed'])
        self.assertEqual(topology['paired_opposite_attachment_edges'],topology['attachment_edges'])
        self.assertTrue(winding_review(self.shell+self.insert,self.sources)['passed'])
        qa=pose_review(self.output,self.sources,self.origins,self.translation,self.seam['seam_points'])
        self.assertTrue(qa['passed']);self.assertEqual(set(qa['poses']),{'local','model'})
        self.assertEqual(len(qa['poses']['model']),15)
        self.assertTrue(all(p['retained_shell_max_error']<1e-6 for checks in qa['poses'].values() for p in checks.values()))

    def test_bad_forehead_fit_is_rejected_despite_closed_seam(self):
        a=self.sources[0]['model'];s=load_source('creator_library/pacs/Chris-Masters.PAC',library=True);b=s['model'];p=partition(b,-.7)
        names=[b['name'] for b in a['bones']];am,bm=bone_matrices(a),bone_matrices(b)
        eye=lambda m,w:np.mean([w[q['index'],:3,3] for q in m['bones'] if q['name'] in ('l_eye','r_eye')],axis=0)
        t=eye(a,am)-eye(b,bm);pa=partition(a)
        sh=records(a,0,names,lambda k:k not in pa.face|pa.attachments);ins=records(b,1,names,lambda k:k in p.face|p.attachments,t)
        stitch_contours(sh,ins,pa,p,t)
        review=winding_review(sh+ins,[self.sources[0],s]);self.assertFalse(review['passed'])
        self.assertEqual(len(review['opposed_source_faces']),2)

    def test_budget_failure_never_writes_candidate(self):
        from tools.creator_facial_trial import package
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'blocked.pac'
            with patch('tools.creator_facial_trial.MAX_BYTES',1),self.assertRaisesRegex(ValueError,'exceeds'):
                package(self.sources[0],self.raw,self.textures,path)
            self.assertFalse(path.exists())

    def test_packaging_readback_and_unrelated_sections_preserved(self):
        from tools.creator_facial_trial import package
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.pac';report=package(self.sources[0],self.raw,self.textures,path)
            self.assertTrue(report['preview_yobj_identical']);self.assertTrue(report['texture_bytes_identical'])
            self.assertTrue(report['within_budget']);self.assertEqual(report['unrelated_stored_sections_identical'],[8])
            self.assertEqual(load_source(path,library=True)['sections'][2],self.raw)
