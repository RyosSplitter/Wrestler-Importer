"""Generated, asset-free regressions for source-authorized skinning contacts."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import numpy as np

from tools.generate_conformance_fixtures import vectors
from tools.psp_mesh_audit import audit_yobj
from tools.jericho_hybrid_trial import pack
from tools.region_mesh import make_regions, pack_regions
from tools.vertex_identity import annotate, influences, point_key, validate_locked
from model_qa.skinning_records import compare


def fixture():
    target=audit_yobj(vectors()['psp-quad.yobj'])
    target.update(bone_count=len(target['bones']),textures=target['texture_names'],model_name=target['report']['model_name'])
    source=dict(bones=copy.deepcopy(target['bones']),bone_count=target['bone_count'],textures=list(target['textures']),texture_names=list(target['textures']),
                meshes=[],preparation_report={},triangle_count=2,vertex_count=4,mesh_count=1)
    for m in target['meshes']:
        source['meshes'].append(dict(index=m['index'],bone_palette=list(m['bone_palette']),
            vertices=[{k:copy.deepcopy(v[k]) for k in ('position','normal','uv','color','weights')} for v in m['vertices']],
            materials=[dict(texture_id=a['texture_id'],triangles=[list(t) for t in a['triangles']]) for a in m['materials']]))
        for v in source['meshes'][-1]['vertices']:v['weights']=[1.,0.]
    return source,target


class SourceSkinningIdentityTests(unittest.TestCase):
    def test_palette_indices_are_resolved_to_global_influences(self):
        a=dict(position=[1,2,3],weights=[.25,.75]);b=dict(position=[1,2,3],weights=[.75,.25])
        self.assertEqual(influences(a,[2,0]),influences(b,[0,2]))
        self.assertEqual(point_key(a,[2,0],3),point_key(b,[0,2],3))
        with self.assertRaises(ValueError):influences(a,[0,0])
        with self.assertRaises(ValueError):influences(dict(weights=[float('nan')]),[0])

    def test_disconnected_identical_source_components_do_not_weld(self):
        source,target=fixture();m=source['meshes'][0];m['vertices']+=copy.deepcopy(m['vertices'])
        m['materials'][0]['triangles'] += [[i+4 for i in t] for t in m['materials'][0]['triangles']]
        source['triangle_count']=4;annotate(source)
        self.assertNotEqual(m['vertices'][0]['skin_domain'],m['vertices'][4]['skin_domain'])
        self.assertNotEqual(point_key(m['vertices'][0],m['bone_palette'],0),point_key(m['vertices'][4],m['bone_palette'],0))
        packed=pack(source,target)
        self.assertEqual(packed['triangle_count'],4);self.assertEqual(packed['vertex_count'],8)

    def test_storage_chunks_join_only_on_a_compatible_manifold_edge(self):
        source,target=fixture();original=source['meshes'][0];parts=[]
        for mi,tri in enumerate(original['materials'][0]['triangles']):
            parts.append(dict(index=mi,bone_palette=list(original['bone_palette']),vertices=[copy.deepcopy(original['vertices'][i]) for i in tri],
                              materials=[dict(texture_id=0,triangles=[[0,1,2]])]))
        source['meshes']=parts;annotate(source)
        self.assertEqual(source['source_skinning_identity']['proven_manifold_component_joins'],1)
        self.assertEqual(pack(source,target)['vertex_count'],4)
        # A UV seam can share geometric points, but not rendering records.
        changed=copy.deepcopy(source)
        for mesh in changed['meshes']:
            for v in mesh['vertices']:
                for k in list(v):
                    if k.startswith('skin_') or k=='source_records':del v[k]
        uv=list(changed['meshes'][1]['vertices'][0]['uv']);uv[0]+=.25
        changed['meshes'][1]['vertices'][0]['uv']=uv;annotate(changed)
        self.assertEqual(changed['source_skinning_identity']['proven_manifold_component_joins'],1)
        self.assertEqual(pack(changed,target)['vertex_count'],5)

    def test_legitimate_coincident_weights_survive_regions_and_packing(self):
        source,target=fixture();other=copy.deepcopy(source['meshes'][0]);other['index']=1
        for v in other['vertices']:v['weights']=[.7,.3]
        source['meshes'].append(other);source['triangle_count']=4;annotate(source)
        self.assertEqual(source['source_skinning_identity']['conflicting_positions'],4)
        regions=make_regions(source);packed=pack(regions,target)
        report=compare(source,packed,poses={'active-joint':{target['bones'][1]['name']:('x',45)}})
        self.assertEqual(report['status'],'pass');self.assertEqual(report['source_conflicting_locations'],4)
        self.assertEqual(report['maximum_motion_error'],0.)
        self.assertEqual(report['maximum_gap_error'],0.)
        self.assertGreater(max(l['poses']['active-joint']['source_gap'] for l in report['locations']),0)
        self.assertEqual(packed['vertex_count'],8)

    def test_drift_in_a_copy_of_the_same_source_point_is_rejected(self):
        source,target=fixture();annotate(source);m=source['meshes'][0]
        v=copy.deepcopy(m['vertices'][0]);v['weights']=[.6,.4];m['vertices'].append(v)
        m['materials'][0]['triangles'][0][0]=4
        with self.assertRaisesRegex(ValueError,'Inconsistent copies'):pack(source,target)

    def test_region_packer_also_rejects_drift_in_a_source_copy(self):
        source,target=fixture();source=make_regions(source);m=source['meshes'][0]
        v=copy.deepcopy(m['vertices'][0]);v['weights']=[.6,.4];m['vertices'].append(v)
        m['materials'][0]['triangles'][0][0]=len(m['vertices'])-1
        with self.assertRaisesRegex(ValueError,'Inconsistent copies'):pack_regions(source)

    def test_locked_source_weights_cannot_be_replaced_or_moved(self):
        v=dict(position=[0,0,0],weights=[.7,.3],skin_locked=True,skin_bind_position=[0,0,0],skin_expected=[[0,.7],[1,.3]])
        validate_locked(v,[0,1]);v['weights']=[.8,.2]
        with self.assertRaisesRegex(ValueError,'weights changed'):validate_locked(v,[0,1])
        v['weights']=[.7,.3];v['position'][0]=.1
        with self.assertRaisesRegex(ValueError,'point moved'):validate_locked(v,[0,1])

    def test_source_reference_does_not_excuse_a_new_branch_or_changed_face(self):
        source,target=fixture();other=copy.deepcopy(source['meshes'][0]);other['index']=1
        source['meshes'].append(other);source['triangle_count']=4
        candidate=copy.deepcopy(source);candidate['meshes'][1]['vertices'][0]['weights']=[.6,.4]
        report=compare(source,candidate,strict=False)
        self.assertEqual(report['status'],'fail')
        self.assertIn('new-coincident-skinning-inconsistency',{i['kind'] for i in report['issues']})
        with self.assertRaises(ValueError):compare(source,candidate)
        for v in source['meshes'][1]['vertices']:v['weights']=[.7,.3]
        candidate=copy.deepcopy(source);candidate['meshes'][1]['materials'][0]['triangles']=[]
        self.assertIn('missing-protected-face',{i['kind'] for i in compare(source,candidate,strict=False)['issues']})

    def test_partial_provenance_is_rejected(self):
        source,target=fixture();source['meshes'][0]['vertices'][0]['skin_id']=[0,0]
        with self.assertRaisesRegex(ValueError,'Incomplete'):annotate(source)

    def test_source_record_qa_rejects_changed_bind_transforms(self):
        source,target=fixture();candidate=copy.deepcopy(source)
        candidate['bones'][0]['local_position']=[.1,0.,0.]
        with self.assertRaisesRegex(ValueError,'bind transforms'):compare(source,candidate)

    def test_contact_budget_precision_cannot_move_geometry_or_weights(self):
        from desktop.precision import bounded_precision
        source,target=fixture()
        for v in source['meshes'][0]['vertices']:v['uv']=[.123456,.345678]
        limited,report=bounded_precision(source,set(),attributes=('normal','uv'))
        for a,b in zip(source['meshes'][0]['vertices'],limited['meshes'][0]['vertices']):
            self.assertEqual(a['position'],b['position']);self.assertEqual(a['weights'],b['weights'])
        self.assertTrue(report['geometry_positions_exact'])

    def test_contact_shape_guards_accept_reader_tuple_indices(self):
        from desktop.core import base_model
        from model_qa.skinning_records import contact_shape_guards
        _,model=base_model(Path(__file__).resolve().parents[1]/'assets/Kurt-Angle-Ring.PAC')
        foot={b['index'] for b in model['bones'] if b['name']=='l_ashi'}
        mesh=next(m for m in model['meshes'] if foot.intersection(m['bone_palette']) and len(m['bone_palette'])>1)
        v=copy.deepcopy(mesh['vertices'][0]);v['weights']=[.5 if i==0 else .5 if i==1 else 0. for i in range(len(mesh['bone_palette']))]
        mesh['vertices'].append(v);annotate(model)
        result=contact_shape_guards(model)
        self.assertIsInstance(result['faces'],list)

    @unittest.skipUnless(shutil.which('blender'),'Blender unavailable')
    def test_actual_blender_retains_distinct_contact_branches(self):
        source,target=fixture();other=copy.deepcopy(source['meshes'][0]);other['index']=1
        for v in other['vertices']:v['weights']=[.7,.3]
        source['meshes'].append(other);source['triangle_count']=4;annotate(source)
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);src=folder/'source.json';dst=folder/'result.json';profile=folder/'profile.json'
            src.write_text(json.dumps(source));profile.write_text(json.dumps(dict(ratios={'Head':.8,'Torso':.65,'Arms':.8,'Legs':.65})))
            result=subprocess.run([shutil.which('blender'),'--background','--factory-startup','--python-exit-code','1','--python',str(root/'desktop/geometry_worker.py'),'--',str(src),str(dst),str(profile)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            packed=pack(json.loads(dst.read_text()),target)
            self.assertEqual(compare(source,packed)['status'],'pass')


if __name__=='__main__':unittest.main()
