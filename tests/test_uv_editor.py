import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from model_creator.core import PARTS,assemble,build,create_project,load_source,read_project
from model_creator.morph.fixtures import donor
from model_creator.uv.document import Document,attach,signature,validate_recipe
from model_creator.uv.native_patch import patch,commit
from tools.psp_mesh_merge_trial import sections


class UVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=donor()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'donor.pac';p.write_bytes(cls.data);cls.source=load_source(p)
        cls.raw=next(r for s,r in sections(cls.data) if s['id']==2)
        cls.textures={n:cls.source['textures'][n.casefold()] for n in cls.source['model']['texture_names']}

    def doc(self):return Document(self.raw,self.textures)

    def test_islands_connect_full_edges_and_keep_disconnected_surfaces_apart(self):
        d=self.doc();seen=set()
        for island in d.islands:
            self.assertFalse(seen&set(island));seen.update(island)
        self.assertEqual(seen,set(range(len(d.faces))))
        # Each fixture front/back quad is one separate continuous surface;
        # native palette aliases on complete matching edges can be joined.
        self.assertTrue(any(len(fs)>=2 for fs in d.islands))
        for fs in d.islands:self.assertEqual(len(set(d.texture_ids[fs])),1)

    def test_region_filters_cover_model_and_isolation_preserves_source(self):
        d=self.doc();from model_creator.uv.document import REGIONS
        groups=[d.visible_faces(0,r) for r in REGIONS[1:]]
        self.assertEqual(sum(map(len,groups)),len(d.visible_faces(0)))
        self.assertTrue(all(groups))
        m=d.model(region='Arms',texture=0,isolate=True)
        self.assertEqual(sum(len(x['triangles']) for mesh in m['meshes'] for x in mesh['materials']),len(groups[2]))
        self.assertEqual(d.baseline,self.doc().baseline)

    def test_select_island_add_toggle_and_shared_record_semantics(self):
        d=self.doc();fs=d.visible_faces(0);d.select_island(fs[0],fs)
        selected=d.selection.copy();self.assertEqual(selected,d.vertices(d.islands[d.face_island[fs[0]]]))
        d.select_island(fs[0],fs,add=True,toggle=True);self.assertFalse(d.selection)
        d.select_island(fs[0],fs);d.select_island(fs[-1],fs,add=True);self.assertTrue(selected<=d.selection)

    def test_transform_centroid_scale_rotate_and_history(self):
        d=self.doc();d.selection=d.vertices(d.islands[0]);ids=sorted(d.selection);before=d.uv.copy()
        d.transform(move=(.2,-.1));np.testing.assert_allclose(d.uv[ids],before[ids]+[.2,-.1],atol=1e-7)
        d.undo();np.testing.assert_array_equal(d.uv,before);d.undo(True)
        d.reset();d.transform(scale=(2,.5),degrees=90)
        center=before[ids].astype(float).mean(0);expected=(before[ids]-center)*[2,.5];expected=np.column_stack((-expected[:,1],expected[:,0]))+center
        np.testing.assert_allclose(d.uv[ids],expected,atol=2e-7)
        self.assertTrue(np.array_equal(d.uv[[i for i in range(len(before)) if i not in ids]],before[[i for i in range(len(before)) if i not in ids]]))
        d.reset();self.assertIsNone(d.recipe())

    def test_drag_uses_baseline_not_cumulative_and_cancels(self):
        d=self.doc();d.selection=d.vertices(d.islands[0]);before=d.uv.copy()
        d.transform(move=(.1,0),baseline=before,history=False);d.transform(move=(.2,0),baseline=before,history=False)
        np.testing.assert_allclose(d.uv[sorted(d.selection)],before[sorted(d.selection)]+[.2,0],atol=1e-7)
        self.assertFalse(d.undo_stack)

    def test_uv_only_native_patch_changes_no_other_bytes_and_readback_exact(self):
        d=self.doc();d.selection=d.vertices(d.islands[0]);d.transform(move=(.13,.05))
        result,proof=patch(self.raw,d.uv);self.assertNotEqual(result,self.raw);self.assertEqual(len(result),len(self.raw))
        self.assertTrue(proof['geometry_topology_weights_bones_materials_exact'])
        from model_creator.native import audit_yobj
        a=copy.deepcopy(d.baseline);b=audit_yobj(result)
        for m in a['meshes']:
            for v in m['vertices']:v.pop('uv')
            m.pop('raw_vertices')
        for m in b['meshes']:
            for v in m['vertices']:v.pop('uv')
            m.pop('raw_vertices')
        self.assertEqual(a,b)
        restored,_=patch(result,d.original);self.assertEqual(restored,self.raw)

    def test_invalid_uvs_and_transforms_do_not_mutate(self):
        d=self.doc();d.selection={0}
        for args in ({'move':(float('nan'),0)},{'scale':(0,1)},{'move':(10000,0)}):
            with self.assertRaises(ValueError):d.transform(**args)
        np.testing.assert_array_equal(d.uv,d.original)
        for uv in (np.zeros((1,2)),np.full_like(d.uv,float('inf'))):
            with self.assertRaises(ValueError):patch(self.raw,uv)

    def test_sparse_recipe_version_binds_to_baseline_and_roundtrips(self):
        d=self.doc();d.selection={0,1};d.transform(move=(.2,0));r=d.recipe()
        self.assertEqual(len(r['edits']),2);other=self.doc();other.restore(json.loads(json.dumps(r)))
        np.testing.assert_array_equal(other.uv,d.uv);self.assertEqual(signature(other.recipe()),signature(r))
        bad=copy.deepcopy(r);bad['baseline_sha256']='0'*64
        with self.assertRaises(ValueError):other.restore(bad)
        bad=copy.deepcopy(r);bad['edits'].append(bad['edits'][0])
        with self.assertRaises(ValueError):validate_recipe(bad)
        bad=copy.deepcopy(r);bad['edits'][0][0]=len(d.uv)
        with self.assertRaises(ValueError):other.restore(bad)

    def test_png_import_uses_serialized_palette_and_locks_alpha_dimensions(self):
        d=self.doc();name=next(iter(self.textures));image=Image.new('RGBA',(32,32),(180,20,30,255))
        image.putpixel((0,0),(250,50,40,255))
        proof=d.import_texture(name,image);self.assertTrue(proof['alpha_exact']);self.assertNotEqual(d.textures,self.textures)
        recipe=d.recipe();other=self.doc();other.restore(recipe);self.assertEqual(other.textures,d.textures)
        for image in (Image.new('RGBA',(16,32)),Image.new('RGBA',(32,32),(0,0,0,0))):
            with self.assertRaises(ValueError):d.import_texture(name,image)
        d.undo();self.assertEqual(d.textures,self.textures);d.undo(True);d.reset();self.assertIsNone(d.recipe())

    def test_mirror_and_distortion_track_uv_collapse_and_orientation(self):
        d=self.doc();d.selection=d.vertices(d.islands[0]);fs=d.islands[0];d.transform(flip='U')
        stretch,flipped=d.distortion();self.assertTrue(any(flipped[fs]));self.assertTrue(all(flipped[f] for f in fs if np.isfinite(stretch[f])))
        d.reset();d.uv[d.faces[0]]=0;stretch,_=d.distortion();self.assertTrue(np.isinf(stretch[0]))

    def test_morph_then_uv_preserves_both_layers(self):
        from model_creator.morph.document import Document as Morph
        from model_creator.morph.native_patch import patch as morph_patch
        m=Morph(self.raw);p,n=m.evaluate({'chest_width':.5});morphed,_=morph_patch(self.raw,p,n)
        d=self.doc();d.selection={0,1};d.transform(move=(.1,0));raw,maps,proof=commit(morphed,self.raw,self.textures,d.recipe())
        result=Document(raw,maps);np.testing.assert_array_equal(result.uv,d.uv)
        positions=np.array([v['position'] for mesh in result.baseline['meshes'] for v in mesh['vertices']])
        np.testing.assert_array_equal(positions,p)
        preview=d.model(m.model({'chest_width':.5}));np.testing.assert_array_equal([v['uv'] for mesh in preview['meshes'] for v in mesh['vertices']],d.uv)

    def test_actual_pac_uv_and_texture_export_project_reset(self):
        from model_creator.morph.document import attach as attach_morph
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);a=t/'A.pac';b=t/'B.pac';a.write_bytes(self.data);b.write_bytes(self.data)
            project=Path(create_project(a,b,t/'Project'));d=self.doc();d.selection={0,1};d.transform(move=(.2,.1))
            d.import_texture('skin',Image.new('RGBA',(32,32),(10,20,190,255)))
            metadata=attach(json.loads(project.read_text()),d.recipe());metadata=attach_morph(metadata,None)
            self.assertEqual(metadata['schema'],'psp-model-creator/3');project.write_text(json.dumps(metadata));read_project(project)
            report=build(project,dict.fromkeys(PARTS,0),t/'Build',resolution=32)
            self.assertEqual(report['uv']['signature'],signature(d.recipe()));self.assertFalse(report['textures_byte_exact'])
            source=load_source(t/'Build/created-model.pac');np.testing.assert_array_equal([v['uv'] for m in source['model']['meshes'] for v in m['vertices']],d.uv)
            self.assertEqual(source['textures']['skin'],d.textures['skin'])
            original=dict((s['id'],r) for s,r in sections(self.data));final=dict((s['id'],r) for s,r in sections(source['data']))
            self.assertEqual(original[8],final[8]);self.assertEqual(a.read_bytes(),self.data)
            project.write_text(json.dumps(attach(metadata,None)))
            build(project,dict.fromkeys(PARTS,0),t/'Reset',resolution=32)
            self.assertEqual((t/'Reset/created-model.pac').read_bytes(),self.data)

    def test_uv_edits_work_on_mixed_part_assembled_baseline(self):
        from model_creator.fixtures import pair
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);paths=[t/'A.pac',t/'B.pac']
            for p,data in zip(paths,pair()):p.write_bytes(data)
            project=create_project(*paths,t/'Project');sources=[load_source(p) for p in paths];choices=dict(Head=1,Torso=0,Arms=1,Legs=0)
            raw,textures,_=assemble(sources,choices);d=Document(raw,textures);d.selection=set(range(10));d.transform(move=(.1,.1))
            r=build(project,choices,t/'Build',resolution=32,uv=d.recipe())
            self.assertTrue(r['uv']['native_readback'])


if __name__=='__main__':unittest.main()
