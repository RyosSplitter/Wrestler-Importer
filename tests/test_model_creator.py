import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from model_creator.core import (PARTS, assemble, build, compatible, create_project, load_source,
                                qa, read_project, skeleton, POSES)
from model_creator.fixtures import pair
from model_creator.parts import clip, triangles
from tools.psp_mesh_audit import audit_yobj


class CreatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.assets=pair()

    def sources(self,root):
        paths=[root/'First.pac',root/'Second.pac']
        for path,data in zip(paths,self.assets):path.write_bytes(data)
        return paths

    def test_project_snapshots_survive_moved_deleted_inputs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);paths=self.sources(root);project=create_project(*paths,root/'Project')
            for path in paths:path.unlink()
            project_data,s=read_project(project)
            self.assertEqual([x['data'] for x in s],self.assets)
            self.assertFalse(project_data['compatibility']['bone_order_identical'])
            (root/'Project').rename(root/'Moved');read_project(root/'Moved/project.json')

    def test_tampered_snapshot_and_manifest_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);project=create_project(*self.sources(root),root/'Project')
            path=root/'Project/source-0.pac';path.write_bytes(path.read_bytes()+b'\0')
            with self.assertRaisesRegex(ValueError,'snapshot'):read_project(project)

    def test_existing_project_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);paths=self.sources(root);create_project(*paths,root/'Project')
            with self.assertRaises(FileExistsError):create_project(*paths,root/'Project')

    def test_same_source_is_byte_exact_including_opaque_payloads(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);project=create_project(*self.sources(root),root/'Project')
            for source in (0,1):
                output=root/f'Build-{source}';r=build(project,{p:source for p in PARTS},output,resolution=64)
                self.assertEqual((output/'created-model.pac').read_bytes(),self.assets[source])
                self.assertTrue(r['geometry_unchanged'])
                self.assertTrue((output/'preview/model.obj').exists())

    def test_mixed_parts_preserve_interior_and_original_textures_under_poses(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);paths=self.sources(root);s=[load_source(p) for p in paths]
            raw,textures,r=assemble(s,dict(Head=1,Torso=0,Arms=1,Legs=0))
            report=qa(raw,r)
            self.assertEqual(len(report['poses']),len(POSES))
            self.assertGreater(r['interior_source_records_verified'],0)
            self.assertTrue(all(x['passed'] for x in r['interior_pose_comparison'].values()))
            self.assertTrue(all(raw in [v for source in s for v in source['textures'].values()] for raw in textures.values()))
            self.assertTrue(all(len(m['bone_palette'])!=1 for m in audit_yobj(raw)['meshes']))

    def test_selected_head_bind_and_parent_mapping_are_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);s=[load_source(p) for p in self.sources(root)]
            raw,_,_=assemble(s,dict(Head=1,Torso=0,Arms=0,Legs=0));result=audit_yobj(raw)
            expected={b['name']:b for b in s[1]['model']['bones']}
            for b in result['bones']:
                if b['name'] in ('atama','atama_d','l_eye','r_eye','d_kuchi'):
                    self.assertEqual(b['local_position'],expected[b['name']]['local_position'])

    def test_changed_body_bind_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);a,b=[load_source(p) for p in self.sources(root)]
            b=copy.deepcopy(b);b['model']['bones'][0]['local_position']=(1,0,0)
            with self.assertRaisesRegex(ValueError,'bind'):compatible(a,b)

    def test_actual_pac_size_enforced_before_output_publication(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);project=create_project(*self.sources(root),root/'Project')
            with patch('model_creator.core.MAX_BYTES',1):
                with self.assertRaisesRegex(ValueError,'exceeding'):build(project,dict.fromkeys(PARTS,0),root/'Oversized',resolution=64)
            self.assertFalse((root/'Oversized').exists())

    def test_invalid_choices_do_not_reach_serializer(self):
        with self.assertRaisesRegex(ValueError,'Choose'):assemble([],dict.fromkeys(PARTS,True))

    def test_clipping_interpolates_uv_and_weights_without_global_welding(self):
        def v(x):return dict(p=np.array([x,0,0.]),uv=np.array([x,0.]),w=np.array([1-x,x]),n=np.array([0,0,1.]),c=np.ones(4)*255,tag=np.array([x,x*x]))
        result=clip([v(0),v(1),dict(v(1),p=np.array([1,1,0.]))],0,.5,1)
        intersection=next(x for x in result if x['p'][0]==.5)
        np.testing.assert_array_equal(intersection['w'],[.5,.5]);np.testing.assert_array_equal(intersection['uv'],[.5,0])

    def test_triangles_keep_collinear_seam_samples(self):
        poly=[{'p':np.array(p,float)} for p in ((0,-6,0),(1,-6.8,0),(.5,-6.8,0),(0,-6.8,0))]
        result=triangles(poly)
        self.assertEqual(len(result),2);self.assertEqual({i for tri in result for i in tri},{0,1,2,3})
