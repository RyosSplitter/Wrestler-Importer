"""Procedural offline-edit fixtures; no model assets or online image tools."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
from PIL import Image,ImageDraw

from desktop.retexture import Document,Layer,Texture,encode_edit,full_quad,warp
from desktop.preview import render
from desktop.texture_optimizer.candidates import read_gim,write_gim
from tools.generate_conformance_fixtures import vectors,pac
from tools.pac_repack import texture_table
from tools.psp_mesh_merge_trial import sections,pose_validation
from tools.yukes_bpe import compress


class RetextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.files=vectors()

    def document(self):return Document(self.files['psp-quad.pac'],'Original.pac')

    def test_unchanged_pac_and_gim_are_byte_exact(self):
        d=self.document();out,r=d.candidate();self.assertEqual(out,d.original)
        t=d.textures[0];raw,r=encode_edit(t.raw,t.original);self.assertEqual(raw,t.raw)

    def test_brush_selection_protection_and_alpha(self):
        d=self.document();t=d.textures[0];before=np.asarray(t.original)
        t.selection=Image.new('L',t.original.size);ImageDraw.Draw(t.selection).rectangle((0,0,15,7),fill=255)
        ImageDraw.Draw(t.protection).rectangle((0,0,3,7),fill=255)
        t.stroke((0,4),(31,4),(10,200,40),2)
        out=np.asarray(t.composite());self.assertTrue(np.array_equal(out[:,:4],before[:,:4]))
        self.assertTrue(np.array_equal(out[:,16:],before[:,16:]));self.assertTrue(np.array_equal(out[:,:,3],before[:,:,3]))
        self.assertTrue((out[4,8,:3]==[10,200,40]).all())

    def test_erase_restores_original_paint(self):
        t=self.document().textures[0];t.stroke((4,4),(4,4),(1,2,3),2);t.stroke((4,4),(4,4),(1,2,3),3,erase=True)
        self.assertTrue(np.array_equal(np.asarray(t.composite()),np.asarray(t.original)))

    def test_recolor_preserves_shading_and_protected_regions(self):
        d=self.document();t=d.textures[0];rgb=np.zeros((8,32,4),np.uint8);rgb[:,:,:3]=np.arange(32)[None,:,None]*5+30;rgb[:,:,3]=255
        t.original=Image.fromarray(rgb);ImageDraw.Draw(t.protection).rectangle((0,0,3,7),fill=255)
        t.recolor((200,20,20));out=np.asarray(t.composite())
        self.assertTrue(np.array_equal(out[:,:4],rgb[:,:4]));self.assertGreater(out[0,28,0],out[0,8,0]);self.assertGreater(out[0,8,0],out[0,8,1])

    def test_import_transform_opacity_and_persistent_protection(self):
        t=self.document().textures[0];t.protection=Image.new('L',t.original.size,255)
        layer=t.import_layer(Image.new('RGBA',(16,16),'red'));self.assertLess(layer.quad[2][0],t.original.width)
        self.assertTrue(np.array_equal(np.asarray(t.composite()),np.asarray(t.original)))
        t.protection=Image.new('L',t.original.size);layer.opacity=0
        self.assertTrue(np.array_equal(np.asarray(t.composite()),np.asarray(t.original)))

    def test_project_roundtrip_retains_layers_masks_art_and_references(self):
        with tempfile.TemporaryDirectory()as temp:
            d=self.document();t=d.textures[0];t.stroke((3,3),(7,3),(4,20,200),1)
            t.import_layer(Image.new('RGBA',(8,8),(240,20,10,190)),'logo');t.protection.putpixel((3,3),255)
            d.references.append(('reference.jpg',Image.new('RGBA',(10,6),'green')));d.color_limit=24;d.touch()
            path=Path(temp)/'project.pspret';d.save(path);self.assertFalse(d.dirty)
            loaded=Document.load(path);self.assertEqual(loaded.original,d.original)
            self.assertEqual(loaded.color_limit,24)
            self.assertTrue(np.array_equal(np.asarray(loaded.textures[0].composite()),np.asarray(t.composite())))
            self.assertEqual(len(loaded.references),1);self.assertEqual(loaded.candidate()[0],d.candidate()[0])
            with self.assertRaises(ValueError):d.save(path)

    def test_project_rejects_modified_asset_and_malformed_layer(self):
        with tempfile.TemporaryDirectory()as temp:
            p=Path(temp)/'a.pspret';d=self.document();d.textures[0].import_layer(Image.new('RGBA',(4,4),'red'));d.save(p)
            with zipfile.ZipFile(p)as z:files={n:z.read(n)for n in z.namelist()}
            meta=json.loads(files['project.json']);meta['textures'][0]['layers'][0]['opacity']=float('nan')
            files['project.json']=json.dumps(meta).encode()
            with zipfile.ZipFile(Path(temp)/'bad.pspret','w')as z:
                for n,b in files.items():z.writestr(n,b)
            with self.assertRaises(ValueError):Document.load(Path(temp)/'bad.pspret')
            files['original.pac']+=b'changed'
            with zipfile.ZipFile(Path(temp)/'tamper.pspret','w')as z:
                for n,b in files.items():z.writestr(n,b)
            with self.assertRaisesRegex(ValueError,'checksum'):Document.load(Path(temp)/'tamper.pspret')

    def test_undo_redo_keeps_distinct_textures_and_masks(self):
        d=self.document();base=np.array(d.textures[0].composite());d.checkpoint()
        d.textures[0].stroke((5,5),(5,5),(10,20,30),2);d.touch();edited=np.array(d.textures[0].composite())
        self.assertTrue(d.undo());self.assertTrue(np.array_equal(np.array(d.textures[0].composite()),base))
        self.assertTrue(d.undo(True));self.assertTrue(np.array_equal(np.array(d.textures[0].composite()),edited))

    def test_encoding_does_not_requantize_skin_outside_edited_area(self):
        ix=np.zeros((32,32),np.uint8);ix[:,16:]=1;pal=np.zeros((256,4),np.uint8);pal[:,3]=255;pal[0,:3]=[160,100,70];pal[1,:3]=[15,15,15]
        raw=write_gim(ix,pal,8);rgba=pal[ix].copy();rgba[:,20:,:3]=[230,10,40]
        edited,r=encode_edit(raw,Image.fromarray(rgba),32);ni,nc=read_gim(edited)
        self.assertEqual(len(raw),len(edited));self.assertTrue(np.array_equal(nc[ni][:,:20],rgba[:,:20]))
        self.assertTrue(np.array_equal(nc[ni][:,20:],rgba[:,20:]));self.assertTrue(r['unchanged_texels_exact'])

    def test_full_native_palette_reports_color_loss_without_changing_unedited_pixels(self):
        ix=np.tile(np.arange(16,dtype=np.uint8),(8,2));pal=np.zeros((16,4),np.uint8);pal[:,3]=255;pal[:,:3]=np.arange(16)[:,None]*15
        raw=write_gim(ix,pal,4);rgba=pal[ix].copy();rgba[0,0,:3]=[255,0,0]
        encoded,r=encode_edit(raw,Image.fromarray(rgba));ni,nc=read_gim(encoded)
        self.assertEqual(r['available_new_palette_slots'],0);self.assertGreater(r['rgb_rmse'],30)
        self.assertTrue(np.array_equal(nc[ni][1:],rgba[1:]))

    def test_alpha_levels_and_rectangular_gim_are_preserved(self):
        t=self.document().textures[0];ix,pal=read_gim(t.raw);pal[:,3]=np.arange(len(pal))*17
        raw=write_gim(ix,pal,4);rgba=pal[ix].copy();rgba[:,:,:3]=[40,50,220]
        encoded,r=encode_edit(raw,Image.fromarray(rgba),16);ni,nc=read_gim(encoded)
        self.assertEqual(ni.shape,ix.shape);self.assertTrue(np.array_equal(nc[ni][:,:,3],rgba[:,:,3]))
        rgba[0,0,3]^=1
        with self.assertRaisesRegex(ValueError,'alpha'):encode_edit(raw,Image.fromarray(rgba))

    def test_all_models_and_nontexture_sections_are_immutable(self):
        f=self.files;table=next(r for s,r in sections(f['psp-quad.pac'])if s['id']==9)
        data=pac([(2,compress(f['psp-quad.yobj'])),(9,compress(table)),(26,f['psp-quad.yobj']),(50,b'opaque')])
        d=Document(data);t=d.textures[0];t.stroke((0,3),(31,3),(20,90,210),3)
        after,r=d.candidate();new=Document(after)
        a={s['id']:r for s,r in sections(data)};b={s['id']:r for s,r in sections(after)}
        for sid in (2,26,50):self.assertEqual(a[sid],b[sid])
        for (_,x),(_,y)in zip(d.models,new.models):
            self.assertTrue(all(v['maximum_position_component_difference']==0 for v in pose_validation(x,y).values()))

    def test_export_rejects_oversize_and_existing_targets(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);d=self.document();d.max_bytes=1
            with self.assertRaisesRegex(ValueError,'No PAC written'):d.export(root/'out.pac')
            self.assertFalse((root/'out.pac').exists());self.assertFalse((root/'out.pac.report.json').exists())
            d.max_bytes=152064;report=d.export(root/'out.pac');self.assertTrue(report['fits'])
            with self.assertRaises(ValueError):d.export(root/'out.pac')

    def test_protected_effect_textures_cannot_be_edited(self):
        t=self.document().textures[0];t.editable=False
        with self.assertRaises(ValueError):t.stroke((0,0),(2,2),(1,2,3),1)
        with self.assertRaises(ValueError):t.recolor((1,2,3))
        with self.assertRaises(ValueError):t.import_layer(Image.new('RGBA',(4,4)))

    def test_warp_registration_and_invalid_crossing_corners(self):
        im=Image.new('RGBA',(16,8),'red');q=[[4,3],[20,3],[20,11],[4,11]]
        out=warp(im,q,(32,16));self.assertEqual(out.getpixel((10,6)),(255,0,0,255));self.assertEqual(out.getpixel((0,0))[3],0)
        with self.assertRaises(ValueError):warp(im,[[0,0],[16,8],[16,0],[0,8]],(32,16))

    def test_rgba_preview_matches_legacy_gim_render_and_does_not_modify_model(self):
        d=self.document();model=d.models[0][1];before=copy.deepcopy(model);t=d.textures[0]
        a=render(model,{'skin':t.raw},resolution=64)
        b=render(model,{},resolution=64,rgba_textures=d.images_for(model))
        self.assertTrue(np.array_equal(a,b));self.assertEqual(model['bone_raw'],before['bone_raw'])
        rotated=render(model,{},resolution=64,rgba_textures=d.images_for(model),yaw=45)
        self.assertEqual(rotated.size,(64,64))

    def test_invalid_inputs_are_bounded(self):
        with self.assertRaises(ValueError):Document(b'not a PAC')
        with self.assertRaises(ValueError):encode_edit(self.document().textures[0].raw,Image.new('RGBA',(8,8)))

    def test_cached_live_preview_matches_full_raster_and_rejects_alpha_change(self):
        from desktop.retexture_preview import TexturePreview
        doc=self.document();model=doc.models[0][1];images=doc.images_for(model)
        for angle in (0,35,180):
            cache=TexturePreview(model,images,yaw=angle,resolution=96)
            for color in (None,[40,90,220]):
                changed={n:a.copy()for n,a in images.items()}
                if color:changed['skin'][:,:,:3]=color
                direct=render(model,{},rgba_textures=changed,yaw=angle,resolution=96)
                self.assertTrue(np.array_equal(direct,cache.image(changed)))
            changed['skin'][0,0,3]^=1
            with self.assertRaises(ValueError):cache.image(changed)


if __name__=='__main__':unittest.main()
