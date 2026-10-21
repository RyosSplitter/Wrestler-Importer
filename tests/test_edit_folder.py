"""Editable-folder conformance fixtures: texture imports must not change native models."""
import json
from pathlib import Path
import tempfile
import struct
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from desktop.edit_folder import export_folder, pack_folder, replace_gim_pixels
from desktop.workspace import inspect_workspace
from desktop.texture_optimizer.candidates import read_gim, write_gim
from tools.generate_conformance_fixtures import vectors, pac
from tools.pac_inspect import parse_textures
from tools.pac_repack import replace_sections
from tools.pac_repack import texture_table
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress


class EditFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.files=vectors()

    def project(self, root, data=None):
        source=root/'Original.pac';source.write_bytes(data or self.files['psp-quad.pac'])
        inspect_workspace(source,root/'inspection',resolution=64)
        folder=root/'Original-edit'
        export_folder(root/'inspection/manifest.json',folder)
        return source,folder

    def change(self, folder):
        image=next((folder/'textures').glob('*.png'))
        with Image.open(image) as source:rgba=np.array(source.convert('RGBA'))
        rgba[:,:,:3]=[5,220,30]
        Image.fromarray(rgba).save(image)
        return image

    def test_unchanged_folder_is_portable_and_round_trips_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,folder=self.project(root)
            data=source.read_bytes();source.unlink()
            moved=root/'Moved project';folder.rename(moved)
            report=pack_folder(moved,root/'Rebuilt.pac')
            self.assertTrue(report['unedited_round_trip_exact'])
            self.assertEqual(report['changed_textures'],0)
            self.assertEqual((root/'Rebuilt.pac').read_bytes(),data)
            self.assertEqual(json.loads(Path(report['report_path']).read_text()),report)

    def test_edited_png_changes_only_texture_payload_and_preserves_all_models(self):
        table=next(raw for s,raw in sections(self.files['psp-quad.pac']) if s['id']==9)
        data=pac([(2,compress(self.files['psp-quad.yobj'])),(9,compress(table)),
                  (26,self.files['psp-quad.yobj']),(27,self.files['psp-quad.yobj']),(50,b'opaque preserved bytes')])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,folder=self.project(root,data);self.change(folder)
            report=pack_folder(folder,root/'Edited.pac')
            self.assertEqual(report['changed_textures'],1)
            a={s['id']:(s['sha256'],raw) for s,raw in sections(data)}
            b={s['id']:(s['sha256'],raw) for s,raw in sections((root/'Edited.pac').read_bytes())}
            self.assertEqual(a.keys(),b.keys())
            for key in a:
                if key!=9:self.assertEqual(a[key],b[key])
            record=parse_textures(b[9][1])[0];gim=b[9][1][record['offset']:record['offset']+record['size']]
            p,c=read_gim(gim);np.testing.assert_array_equal(c[p][:,:,:3],np.broadcast_to([5,220,30],c[p][:,:,:3].shape))
            self.assertEqual(source.read_bytes(),data)

    def test_palette_quantization_keeps_alpha_and_gim_headers_exact(self):
        original=self.files['skin-t4.gim'];p,c=read_gim(original)
        rgba=np.zeros((*p.shape,4),np.uint8)
        y,x=np.indices(p.shape)
        rgba[:,:,0]=(x*13+y*27)%256;rgba[:,:,1]=(x*31)%256;rgba[:,:,2]=(y*17)%256
        rgba[:,:,3]=np.where((x+y)%2,255,0)
        encoded,report=replace_gim_pixels(original,rgba)
        q,d=read_gim(encoded)
        self.assertEqual(len(encoded),len(original));self.assertEqual(len(d),16)
        self.assertEqual(encoded[:128],original[:128])
        np.testing.assert_array_equal(d[q][:,:,3],rgba[:,:,3])
        self.assertTrue(report['alpha_exact']);self.assertGreater(report['rgb_rmse'],0)

    def test_padded_rectangular_t8_and_transparent_images_keep_existing_contract(self):
        for bits,shape in ((4,(8,8)),(8,(8,32)),(8,(32,64))):
            p=np.zeros(shape,np.uint8);c=np.zeros((1<<bits,4),np.uint8)
            c[0]=[255,20,10,255]
            original=write_gim(p,c,bits)
            rgba=c[p].copy();rgba[:shape[0]//2,:,3]=0;rgba[:,:,1]=77
            encoded,report=replace_gim_pixels(original,rgba)
            q,d=read_gim(encoded)
            np.testing.assert_array_equal(d[q],rgba)
            self.assertEqual(len(encoded),len(original))

    def test_too_many_alpha_levels_are_rejected(self):
        original=self.files['skin-t4.gim'];p,c=read_gim(original)
        rgba=c[p].copy();rgba[:,:,3]=np.arange(p.size,dtype=np.uint8).reshape(p.shape)
        with self.assertRaisesRegex(ValueError,'alpha levels'):replace_gim_pixels(original,rgba)

    def test_wrong_size_geometry_material_and_snapshot_edits_are_rejected(self):
        for kind in ('size','obj','yobj','mtl','raw','snapshot','extra_obj'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);_,folder=self.project(root)
                if kind=='size':Image.new('RGBA',(64,64)).save(next((folder/'textures').glob('*.png')))
                elif kind in ('obj','yobj','mtl'):
                    path=next((folder/'models').rglob('*.'+kind));path.write_bytes(path.read_bytes()+b'edited')
                elif kind=='raw':
                    path=next((folder/'textures').glob('*.bin'));path.write_bytes(b'changed')
                elif kind=='snapshot':(folder/'original.pac').write_bytes(b'changed')
                else:(folder/'Extra.obj').write_text('v 1 2 3')
                with self.assertRaises((ValueError,OSError)):pack_folder(folder,root/'Bad.pac')
                self.assertFalse((root/'Bad.pac').exists())

    def test_final_measured_size_is_enforced_even_if_project_budget_is_edited(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,folder=self.project(root);self.change(folder)
            metadata=json.loads((folder/'project.json').read_text());metadata['max_pac_bytes']=9999999
            (folder/'project.json').write_text(json.dumps(metadata))
            from desktop.limits import IN_RING_MAX_PAC_BYTES
            def oversized(source,replacements):return replace_sections(source,replacements)+bytes(IN_RING_MAX_PAC_BYTES)
            with patch('desktop.edit_folder.replace_sections',side_effect=oversized):
                with self.assertRaisesRegex(ValueError,'budget'):pack_folder(folder,root/'Too-big.pac')
            self.assertFalse((root/'Too-big.pac').exists());self.assertFalse((root/'Too-big.pac.report.json').exists())

    def test_existing_destinations_and_projects_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,folder=self.project(root)
            with self.assertRaises(FileExistsError):export_folder(root/'inspection/manifest.json',folder)
            with self.assertRaises(ValueError):pack_folder(folder,source)
            with self.assertRaises(ValueError):pack_folder(folder,folder/'Original.pac')
            output=root/'Accepted.pac';output.write_bytes(b'accepted')
            with self.assertRaises(ValueError):pack_folder(folder,output)
            self.assertEqual(output.read_bytes(),b'accepted')

    def test_effect_controller_textures_cannot_be_requantized(self):
        model=bytearray(self.files['psp-quad.yobj'])
        texture_start=struct.unpack_from('<I',model,44)[0]+8
        model[texture_start:texture_start+16]=b'blood'.ljust(16,b'\0')
        table=texture_table(['blood'],[self.files['skin-t4.gim']],gim_reader=read_gim)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,folder=self.project(root,pac([(2,bytes(model)),(9,table)]))
            self.change(folder)
            with self.assertRaisesRegex(ValueError,'read-only'):pack_folder(folder,root/'Bad.pac')
            self.assertFalse((root/'Bad.pac').exists())

    def test_concurrent_png_save_is_detected_before_publishing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,folder=self.project(root);png=self.change(folder)
            def changed(source,replacements):
                with Image.open(png) as image:
                    size=image.size
                Image.new('RGBA',size,(200,10,10,255)).save(png)
                return replace_sections(source,replacements)
            with patch('desktop.edit_folder.replace_sections',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed during packing'):pack_folder(folder,root/'Bad.pac')
            self.assertFalse((root/'Bad.pac').exists())


if __name__=='__main__':unittest.main()
