"""Synthetic format, selection, provenance and failure-isolation checks."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.adapters import adapter
from desktop.core import Request,run_job,digest
from tests.test_jbi_rig import fixture
from tests.test_sym_source import archive
from tools.generate_conformance_fixtures import pac
from tools.jbi_fixture import atlas
from tools.jbi_source import select,read,decode,decoded_textures
from tools.portable_fixture import encode


def costume(extras=()):
    return pac([(1,atlas()),(2,encode(fixture(2))),*extras])


class JbiAdapterTests(unittest.TestCase):
    def test_archive_selects_requested_entry_without_filename_heuristics(self):
        data=archive(ids=(0x12,0xabcd))
        first,catalogue=select(data)
        self.assertEqual(catalogue['selected_entry'],'0012')
        second,info=select(data,'ABCD')
        self.assertEqual(info['selected_entry'],'abcd');self.assertEqual(len(info['entries']),2)
        self.assertEqual(first,second)  # synthetic payloads identical, IDs still explicit
        for ident in ('0000','abcd0','../x',12):
            with self.subTest(ident=ident),self.assertRaises(ValueError):select(data,ident)

    def test_standalone_rejects_archive_selector_and_never_aliases_hctp(self):
        raw=costume();selected,info=select(raw)
        self.assertEqual(raw,selected);self.assertEqual(info['entries'],[])
        with self.assertRaisesRegex(ValueError,'no archive entry'):select(raw,'0000')
        self.assertNotEqual(type(adapter('jbi')),type(adapter('hctp')))
        with self.assertRaisesRegex(ValueError,'TIM2'):decode(pac([(2,encode(fixture(2)))]))

    def test_unknown_extras_and_duplicate_model_ids_are_not_dropped(self):
        blob=encode(fixture(2))
        with self.assertRaisesRegex(ValueError,'Unsupported JBI accessory'):decode(costume([(5,blob)]))
        with self.assertRaisesRegex(ValueError,'Duplicate JBI'):decode(costume([(2,blob)]))

    def test_wrong_side_accessory_weights_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'elbow-pad contract'):decode(costume([(6,encode(fixture(2)))]))

    def test_source_inspection_is_readonly_and_exports_original_chart_samples(self):
        raw=costume()
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'unrelated-name.PAC';source.write_bytes(raw)
            result=adapter('jbi').inspect(source,Path(tmp)/'previews')
            self.assertEqual(result['model_count'],1);self.assertEqual(result['accessory_sections'],[])
            self.assertEqual(result['source_sha256'],digest(source));self.assertEqual(source.read_bytes(),raw)
            bundle=read(raw);decoded=decoded_textures(bundle)
            self.assertEqual(len(result['texture_previews']),len(decoded))
            self.assertLess(bundle['atlas']['maximum_sample_rgba_error'],1e-7)
            self.assertTrue(all(Path(r['png']).is_file() for r in result['texture_previews']))

    def test_palette_and_source_fields_are_not_assumed_to_be_hctp_rtx3(self):
        bundle=read(costume());rows=decoded_textures(bundle)
        self.assertEqual(rows[0][4]['bits_per_index'],8)
        self.assertEqual(rows[0][4]['palette_entries'],256)
        self.assertFalse(rows[0][4]['alpha_forced_opaque'])

    def test_priority_review_is_bound_to_archive_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a.pac',Path(tmp)/'b.pac';a.write_bytes(costume());b.write_bytes(costume())
            r=Request(str(a),str(b),source_format='jbi',source_entry='0100',texture_mode='Priority Selection',
                priority_textures=('chart_00',),texture_review_sha256=digest(a),texture_review_entry='0000')
            with self.assertRaisesRegex(ValueError,'costume changed'):r.validate()
            with self.assertRaisesRegex(ValueError,'Legacy textures'):
                Request(str(a),str(b),source_format='jbi',texture_mode='Legacy').validate()
            with self.assertRaisesRegex(ValueError,'Only JBI'):
                Request(str(a),str(b),source_entry='0100').validate()

    def test_job_dispatch_keeps_hctp_preparation_out_of_jbi(self):
        request=Request('source.pac','base.pac',source_format='jbi')
        with patch('desktop.jbi_job.run_job',return_value={'isolated':'jbi'}) as job, \
             patch('desktop.core.prepare',side_effect=AssertionError('HCTP path used')):
            result=run_job(request,'work')
        self.assertEqual(result,{'isolated':'jbi'});self.assertIs(job.call_args.args[0],request)

    def test_bad_atlas_is_rejected_before_preview_or_conversion(self):
        with self.assertRaises(ValueError):decode(pac([(1,b'TIM2 corrupt'),(2,encode(fixture(2)))]))


if __name__=='__main__':unittest.main()
