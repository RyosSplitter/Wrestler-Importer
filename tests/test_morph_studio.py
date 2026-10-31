import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from model_creator.core import PARTS,build,create_project,load_source,read_project
from model_creator.morph.deform import CONTROLS,parameters
from model_creator.morph.document import Document,PAIR_SCHEMA,attach,signature,validate_recipe
from model_creator.morph.fixtures import donor
from model_creator.morph.native_patch import patch as patch_native
from tools.psp_mesh_merge_trial import sections


class MorphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=donor();cls.raw=next(r for s,r in sections(cls.data) if s['id']==2)

    def test_zero_morph_is_identity_without_runtime(self):
        d=Document(self.raw);p,n=d.evaluate()
        np.testing.assert_array_equal(p,d.points);np.testing.assert_array_equal(n,d.normals)
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);a=t/'A.pac';b=t/'B.pac';a.write_bytes(self.data);b.write_bytes(self.data)
            project=create_project(a,b,t/'Project')
            r=build(project,dict.fromkeys(PARTS,0),t/'Build',resolution=32,blender='/missing',morph=d.recipe())
            self.assertEqual((t/'Build/created-model.pac').read_bytes(),self.data)
            self.assertNotIn('morph',r)

    def test_reversible_and_non_cumulative(self):
        d=Document(self.raw);d.set({'chest_width':.5});a,_=d.evaluate()
        self.assertGreater(np.max(np.abs(a-d.points)),.01)
        d.set({'chest_width':-.5});d.set({'chest_width':.5});b,_=d.evaluate()
        np.testing.assert_array_equal(a,b)
        d.undo();self.assertEqual(d.values['chest_width'],-.5)
        d.undo(True);np.testing.assert_array_equal(d.evaluate()[0],a)
        d.set({});np.testing.assert_array_equal(d.evaluate()[0],d.points)

    def test_invalid_controls_and_recipes_rejected(self):
        for value in (True,float('nan'),float('inf'),2,'1'):
            with self.assertRaises(ValueError):parameters({'waist':value})
        with self.assertRaises(ValueError):parameters({'nose':.5})
        r=Document(self.raw).recipe();r['engine']='unknown'
        with self.assertRaises(ValueError):validate_recipe(r)

    def test_native_patch_preserves_topology_uv_weights_bones_and_opaque_bytes(self):
        d=Document(self.raw);p,n=d.evaluate({'chest_width':.6})
        raw,proof=patch_native(self.raw,p,n)
        self.assertNotEqual(raw,self.raw);self.assertEqual(len(raw),len(self.raw))
        self.assertTrue(proof['topology_uv_weights_materials_bones_exact'])
        self.assertGreater(proof['changed_bytes'],0)
        self.assertEqual(d.raw,self.raw)

    def test_bad_native_results_and_folded_faces_block(self):
        d=Document(self.raw)
        with self.assertRaises(ValueError):patch_native(self.raw,np.zeros((1,3)),d.normals)
        p=d.points.copy();p[:,0]*=-1
        with self.assertRaises(ValueError):d.check_geometry(p)

    def test_project_version_and_fingerprint_roundtrip(self):
        d=Document(self.raw);d.set({'chest_depth':.4});r=d.recipe()
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);a=t/'A.pac';b=t/'B.pac';a.write_bytes(self.data);b.write_bytes(self.data)
            project=Path(create_project(a,b,t/'Project'));p=json.loads(project.read_text())
            p=attach(p,r);self.assertEqual(p['schema'],PAIR_SCHEMA);project.write_text(json.dumps(p))
            restored,_=read_project(project);other=Document(self.raw);other.restore(restored['morph'])
            self.assertEqual(signature(other.recipe()),signature(r))
            zero=attach(p,None);self.assertEqual(zero['schema'],'psp-model-creator/1');self.assertNotIn('morph',zero)
        r['baseline_sha256']='0'*64
        with self.assertRaises(ValueError):d.restore(r)

    def test_auxiliary_and_mixed_morphs_rejected_before_worker(self):
        from tools.pac_repack import replace_sections
        d=Document(self.raw);d.set({'chest_width':.5})
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);a=t/'A.pac';b=t/'B.pac';a.write_bytes(self.data);b.write_bytes(self.data)
            project=create_project(a,b,t/'Project')
            with self.assertRaisesRegex(ValueError,'Whole donor'):
                build(project,dict(Head=0,Torso=0,Arms=1,Legs=0),t/'Build',resolution=32,morph=d.recipe())

    def test_blender_roundtrip_and_actual_export(self):
        from desktop.blender_runtime import resolve
        try:runtime=resolve()
        except ValueError:self.skipTest('Blender not installed; frozen smoke validates selected runtime')
        from model_creator.morph.blender_bridge import commit
        d=Document(self.raw);d.set({'chest_width':.5})
        raw,r=commit(self.raw,d.recipe(),runtime=runtime)
        self.assertEqual(len(raw),len(self.raw));self.assertEqual(len(r['qa']['poses']),20)
        self.assertLess(r['blender_preview_error'],d.height*2e-6)
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);a=t/'A.pac';b=t/'B.pac';a.write_bytes(self.data);b.write_bytes(self.data)
            project=create_project(a,b,t/'Project')
            result=build(project,dict.fromkeys(PARTS,0),t/'Build',resolution=32,morph=d.recipe(),blender=runtime)
            self.assertEqual(result['morph']['signature'],signature(d.recipe()))
            old={s['id']:r for s,r in sections(self.data)};new={s['id']:r for s,r in sections((t/'Build/created-model.pac').read_bytes())}
            for sid in old:
                if sid!=2:self.assertEqual(old[sid],new[sid])


if __name__=='__main__':unittest.main()
