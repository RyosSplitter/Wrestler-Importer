"""Mutable donor-library transactions and persistence; synthetic data only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_creator.core import digest
from model_creator.fixtures import pair
from model_creator.library import Library, add_donors, catalog_lock


class DonorImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.assets=pair()

    def setup_library(self,root):
        library=root/'Library';library.mkdir();(library/'pacs').mkdir()
        (library/'pacs/original.pac').write_bytes(self.assets[0])
        catalog=dict(schema='psp-model-creator.library/1',models=[dict(file='pacs/original.pac',label='Original',sha256=digest(self.assets[0]))])
        (library/'catalog.json').write_text(json.dumps(catalog))
        incoming=root/'New donor.PAC';incoming.write_bytes(self.assets[1])
        return library,incoming

    def test_add_survives_removed_input_and_restart_with_native_previews(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library,path=self.setup_library(root);before=(library/'catalog.json').read_bytes()
            report=add_donors([path],library);path.unlink();lib=Library(library)
            self.assertEqual(len(report['added']),1);self.assertEqual(len(lib.entries),2)
            self.assertEqual(lib.source(1)['data'],self.assets[1])
            self.assertEqual(Path(report['catalog_backup']).read_bytes(),before)
            for view in ('front','back'):self.assertTrue((library/lib.entries[1]['previews'][view]).is_file())
            self.assertEqual((library/'pacs/original.pac').read_bytes(),self.assets[0])

    def test_duplicates_by_content_do_not_change_catalog_or_original(self):
        with tempfile.TemporaryDirectory() as temp:
            library,path=self.setup_library(Path(temp));add_donors([path],library)
            previous=(library/'catalog.json').read_bytes();alias=path.with_name('Renamed.pac');alias.write_bytes(path.read_bytes())
            result=add_donors([path,alias],library)
            self.assertEqual(len(result['duplicates']),2);self.assertFalse(result['added']);self.assertEqual(previous,(library/'catalog.json').read_bytes())
            self.assertEqual(path.read_bytes(),self.assets[1])

    def test_rejected_input_does_not_hide_good_input_in_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library,path=self.setup_library(root);bad=root/'PS2-or-damaged.pac';bad.write_bytes(b'not a PAC')
            r=add_donors([bad,path,root/'missing.pac'],library)
            self.assertEqual(len(r['added']),1);self.assertEqual(len(r['rejected']),2);self.assertEqual(len(Library(library).entries),2)

    def test_same_label_with_different_contents_gets_distinct_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library,path=self.setup_library(root)
            other=root/'another';other.mkdir();same_name=other/path.name;same_name.write_bytes(self.assets[1]+b'\0'*16)
            result=add_donors([path,same_name],library)
            self.assertEqual(len(result['added']),2);entries=Library(library).entries
            self.assertEqual(entries[1]['label'],entries[2]['label']);self.assertNotEqual(entries[1]['file'],entries[2]['file'])

    def test_failed_catalog_commit_rolls_back_new_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library,path=self.setup_library(root);before=(library/'catalog.json').read_bytes()
            with patch('model_creator.library.os.replace',side_effect=OSError('simulated locked catalog')):
                with self.assertRaisesRegex(OSError,'locked'):add_donors([path],library)
            self.assertEqual(before,(library/'catalog.json').read_bytes());self.assertEqual(len(list((library/'pacs').glob('*.pac'))),1)
            self.assertEqual(Library(library).source(0)['data'],self.assets[0]);self.assertFalse(list(library.glob('.catalog-*.tmp')))

    def test_parallel_import_cannot_lose_catalog_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            library,path=self.setup_library(Path(temp))
            with catalog_lock(library):
                with self.assertRaisesRegex(ValueError,'Another donor import'):add_donors([path],library)
            self.assertEqual(len(add_donors([path],library)['added']),1)

    def test_import_does_not_enforce_conversion_cap_or_mutate_native_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            library,path=self.setup_library(Path(temp));path.write_bytes(self.assets[1]+bytes(150000))
            result=add_donors([path],library);lib=Library(library)
            self.assertEqual(len(result['added']),1);self.assertTrue(lib.entries[1]['preview_only_over_budget'])
            self.assertEqual(lib.source(1)['data'],path.read_bytes())

    def test_modified_registered_object_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            library,path=self.setup_library(Path(temp));target=library/'pacs'/('user-'+digest(path.read_bytes())+'.pac');target.write_bytes(b'unrelated data')
            before=(library/'catalog.json').read_bytes();r=add_donors([path],library)
            self.assertFalse(r['added']);self.assertEqual(len(r['rejected']),1);self.assertEqual(target.read_bytes(),b'unrelated data');self.assertEqual(before,(library/'catalog.json').read_bytes())

    def test_explicit_oversize_policy_exports_with_exact_native_bytes_and_warning(self):
        from model_creator.core import PARTS,build,load_source
        from model_creator.library import create_project
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library,path=self.setup_library(root);source=load_source(path,library=True)
            project=create_project([source],dict.fromkeys(PARTS,0),root/'Project')
            with patch('model_creator.core.MAX_BYTES',1):
                report=build(project,dict.fromkeys(PARTS,0),root/'Build',resolution=64,library=True,allow_oversize=True)
            self.assertFalse(report['within_budget']);self.assertEqual(report['budget_warning']['over_by_bytes'],len(source['data'])-1)
            self.assertEqual((root/'Build/created-model.pac').read_bytes(),source['data'])
            self.assertIn('OVER BUDGET',(root/'Build/README.txt').read_text())
            self.assertTrue(report['qa']['native_structural_audit']['offsets_ranges_indices_palettes_weights_valid'])

    def test_allow_oversize_does_not_allow_out_of_range_indices(self):
        import struct
        from model_creator.core import PARTS,build
        from tools.psp_mesh_merge_trial import sections
        from tools.psp_mesh_audit import audit_yobj
        from tools.pac_repack import replace_sections
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library,path=self.setup_library(root)
            raw=bytearray(next(r for s,r in sections(self.assets[1]) if s['id']==2));model=audit_yobj(bytes(raw))
            start=model['report']['mesh_reports'][0]['submeshes'][0]['index_ranges'][0]['start'];struct.pack_into('<H',raw,start,65535)
            damaged=replace_sections(self.assets[1],{2:bytes(raw)});project=root/'Project';project.mkdir();(project/'source-0.pac').write_bytes(damaged)
            (project/'project.json').write_text(json.dumps(dict(schema='psp-model-creator.library-project/1',sources=[dict(file='source-0.pac',sha256=digest(damaged),label='Damaged')],selections=dict.fromkeys(PARTS,0))))
            with self.assertRaisesRegex(ValueError,'Index outside'):build(project/'project.json',dict.fromkeys(PARTS,0),root/'No',resolution=64,library=True,allow_oversize=True)
            self.assertFalse((root/'No').exists())
