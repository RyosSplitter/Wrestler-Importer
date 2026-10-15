"""Generated conformance data only; no game assets or graphical display needed."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from desktop.workspace import inspect_workspace, copy_original, export_previews, verified_snapshot
from tools.generate_conformance_fixtures import vectors, pac
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = vectors()

    def inspect(self, root, data=None):
        source = root/'input.pac'
        source.write_bytes(data if data is not None else self.files['psp-quad.pac'])
        result = inspect_workspace(source, root/'workspace', resolution=64)
        return source, root/'workspace/manifest.json', result

    def test_all_models_and_opaque_data_survive_byte_identical_copy(self):
        texture = next(raw for section,raw in sections(self.files['psp-quad.pac']) if section['id']==9)
        data = pac([(2, compress(self.files['psp-quad.yobj'])), (9, texture),
                    (26, self.files['psp-quad.yobj']), (27, self.files['psp-quad.yobj']),
                    (50, b'opaque data must stay verbatim')])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source, path, result = self.inspect(root, data)
            self.assertEqual([m['section'] for m in result['models']], [2,26,27])
            self.assertEqual([m['triangles'] for m in result['models']], [2,2,2])
            self.assertEqual(result['sections'][-1]['id'],50)
            for model in result['models']:
                self.assertEqual((path.parent/model['yobj']).read_bytes(),self.files['psp-quad.yobj'])
            copy_original(path,root/'copy.pac')
            self.assertEqual((root/'copy.pac').read_bytes(),data)
            self.assertEqual(source.read_bytes(),data)
            self.assertTrue(result['converter_export_profile']['passed'])

    def test_preview_zip_resolves_obj_materials_without_losing_native_rig(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            _,path,result=self.inspect(root)
            model=result['models'][0]
            self.assertEqual(len(model['views']),5)
            export_previews(path,root/'preview.zip')
            with zipfile.ZipFile(root/'preview.zip') as archive:
                self.assertEqual(archive.read('models/model_0000/model.yobj'),self.files['psp-quad.yobj'])
                self.assertIn('mtllib preview.mtl',archive.read('models/model_0000/model.obj').decode())
                self.assertIn('map_Kd ../../textures/texture_0000.png',archive.read('models/model_0000/preview.mtl').decode())
                self.assertIn('textures/texture_0000.png',archive.namelist())
                self.assertNotIn('original.pac',archive.namelist())
                self.assertEqual(json.loads(archive.read('models/model_0000/audit.json'))['bones'],model['bones'])

    def test_snapshot_mutation_and_input_or_existing_destination_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source,path,_=self.inspect(root)
            with self.assertRaisesRegex(ValueError,'original input'):copy_original(path,source)
            output=root/'accepted.pac';output.write_bytes(b'accepted baseline')
            with self.assertRaises(FileExistsError):copy_original(path,output)
            self.assertEqual(output.read_bytes(),b'accepted baseline')
            (path.parent/'original.pac').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'snapshot changed'):verified_snapshot(path)
            with self.assertRaises(ValueError):export_previews(path,root/'bad.zip')
            self.assertFalse((root/'bad.zip').exists())

    def test_embedded_texture_names_never_become_paths(self):
        texture=bytearray(next(raw for section,raw in sections(self.files['psp-quad.pac']) if section['id']==9))
        texture[16:32]=b'../outside'.ljust(16,b'\0')
        data=pac([(2,self.files['psp-quad.yobj']),(9,bytes(texture))])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            _,path,result=self.inspect(root,data)
            self.assertEqual(result['textures'][0]['name'],'../outside')
            self.assertEqual(result['textures'][0]['png'],'textures/texture_0000.png')
            self.assertFalse((root/'outside.png').exists())
            self.assertTrue(result['models'][0]['preview_error'])
            self.assertFalse(result['converter_export_profile']['passed'])

    def test_observed_uppercase_table_names_resolve_lowercase_model_references(self):
        texture=bytearray(next(raw for section,raw in sections(self.files['psp-quad.pac']) if section['id']==9))
        texture[16:32]=b'SKIN'.ljust(16,b'\0')
        with tempfile.TemporaryDirectory() as directory:
            _,_,result=self.inspect(Path(directory),pac([(2,self.files['psp-quad.yobj']),(9,bytes(texture))]))
            self.assertEqual(len(result['models'][0]['views']),5)
            self.assertIsNone(result['models'][0]['preview_error'])
            self.assertEqual(result['textures'][0]['name'],'SKIN')

    def test_unsupported_yobj_is_reported_without_rewriting_it(self):
        data=pac([(2,self.files['hctp-quad.yobj'])])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source,path,result=self.inspect(root,data)
            self.assertTrue(result['models'][0]['error'])
            self.assertTrue(result['findings'])
            self.assertFalse(result['converter_export_profile']['passed'])
            self.assertEqual(source.read_bytes(),data)
            self.assertEqual((path.parent/result['models'][0]['yobj']).read_bytes(),self.files['hctp-quad.yobj'])

    def test_native_inspection_does_not_claim_conversion_size_limit_is_universal(self):
        data=self.files['psp-quad.pac']+bytes(150000)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            _,_,result=self.inspect(root,data)
            self.assertFalse(result['within_conversion_budget'])
            self.assertEqual(result['game_compatibility'],'Not established by structural inspection.')
            self.assertEqual(result['models'][0]['triangles'],2)

    def test_truncated_container_and_existing_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source,path,_=self.inspect(root)
            with self.assertRaises(FileExistsError):inspect_workspace(source,path.parent,resolution=64)
            source.write_bytes(b'PAC '+struct.pack('<I',50000))
            with self.assertRaises(ValueError):inspect_workspace(source,root/'invalid',resolution=64)
            self.assertFalse((root/'invalid').exists())


if __name__=='__main__':unittest.main()
