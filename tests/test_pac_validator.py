"""Standalone validator: real native fixtures, exact preservation and rejection."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from desktop.source_reference_qa import validate_pac
from tools.generate_conformance_fixtures import vectors,pac
from tools.psp_mesh_merge_trial import sections
from tools.psp_mesh_audit import audit_yobj
from tests.test_portable_skinning import one_slot_model


class ValidatorTests(unittest.TestCase):
    def run_case(self, data, root, **options):
        source=root/'Input.pac';source.write_bytes(data)
        report=validate_pac(source,root/'qa',resolution=96,samples=2000,**options)
        self.assertEqual(source.read_bytes(),data)
        self.assertEqual((root/'qa/original.pac').read_bytes(),data)
        self.assertTrue(report['input_unchanged'])
        self.assertTrue((root/'qa/report.html').is_file())
        return report

    def test_valid_pac_is_not_rebuilt_and_shape_is_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(vectors()['psp-quad.pac'],Path(t))
            self.assertIsNone(r['repaired_pac']);self.assertEqual(r['repairs'],[])
            self.assertEqual(r['before']['blocking_findings'],[])
            self.assertIn('unknown',r['anatomy_status'])
            self.assertTrue(r['before']['models'][0]['analytical']['poses'])

    def test_known_one_slot_repair_preserves_geometry_and_auxiliaries(self):
        f=vectors();table=next(raw for s,raw in sections(f['psp-quad.pac']) if s['id']==9)
        data=pac([(2,one_slot_model()),(9,table),(26,f['psp-quad.yobj']),(50,b'opaque')])
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(data,Path(t))
            self.assertIsNotNone(r['repaired_pac'],r)
            a={s['id']:raw for s,raw in sections(data)}
            b={s['id']:raw for s,raw in sections(Path(r['repaired_pac']).read_bytes())}
            for key in (9,26,50):self.assertEqual(a[key],b[key])
            evidence=r['repairs'][0]['evidence']
            self.assertEqual(evidence['changed_meshes'],1)
            self.assertEqual(evidence['changed_models'][0]['poses']['status'],'pass')
            self.assertFalse((Path(t)/'qa/candidate-for-qa.pac').exists())

    def test_alignment_repair_preserves_stored_payloads(self):
        f=vectors();raw=f['psp-quad.yobj'];entries=[(s['id'],r) for s,r in sections(f['psp-quad.pac'])]
        header=bytearray(b'PAC '+struct.pack('<I',len(entries)));payload=b''
        for sid,r in entries:
            header+=struct.pack('<H',sid)+len(payload).to_bytes(3,'little')+len(r).to_bytes(3,'little');payload+=r
        data=bytes(header)+payload
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(data,Path(t))
            self.assertIsNotNone(r['repaired_pac'],r)
            self.assertTrue(r['after']['aligned_file'])
            self.assertEqual(next(sections(Path(r['repaired_pac']).read_bytes()))[1],raw)

    def test_unsafe_gap_is_not_discarded(self):
        entries=[(s['id'],r) for s,r in sections(vectors()['psp-quad.pac'])]
        header=bytearray(b'PAC '+struct.pack('<I',len(entries)));payload=b'X'
        for sid,raw in entries:
            header+=struct.pack('<H',sid)+len(payload).to_bytes(3,'little')+len(raw).to_bytes(3,'little');payload+=raw
        data=bytes(header)+payload
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(data,Path(t))
            self.assertIsNone(r['repaired_pac']);self.assertTrue(r['repair_failures'])

    def test_invalid_container_and_budget_produce_report_without_repair(self):
        for data,options in ((b'broken',{}),(vectors()['psp-quad.pac'],dict(max_bytes=32))):
            with tempfile.TemporaryDirectory() as t:
                r=self.run_case(data,Path(t),**options)
                self.assertIsNone(r['repaired_pac']);self.assertIn('withheld',r['status'])

    def test_check_only_does_not_fix_known_layout(self):
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(pac([(2,one_slot_model())]),Path(t),repair=False)
            self.assertIsNone(r['repaired_pac']);self.assertEqual(r['repairs'],[])

    def test_optional_reference_runs_existing_qa_and_failure_withholds(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ref=root/'hctp.pac';ref.write_bytes(b'opaque mocked reference')
            with patch('model_qa.pipeline.run',return_value=dict(flags=[])) as qa:
                r=self.run_case(vectors()['psp-quad.pac'],root,reference=ref)
                self.assertEqual(qa.call_count,1);self.assertTrue(r['reference_qa']['regression_check_passed'])
            self.assertEqual(ref.read_bytes(),b'opaque mocked reference')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ref=root/'hctp.pac';ref.write_bytes(b'bad')
            with patch('model_qa.pipeline.run',side_effect=ValueError('reference unsupported')):
                r=self.run_case(vectors()['psp-quad.pac'],root,reference=ref)
                self.assertIn('withheld',r['status'])

    def test_existing_result_directory_not_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.run_case(vectors()['psp-quad.pac'],root)
            original=(root/'qa/report.json').read_bytes()
            with self.assertRaises(FileExistsError):validate_pac(root/'Input.pac',root/'qa')
            self.assertEqual((root/'qa/report.json').read_bytes(),original)

    def test_invalid_index_and_weight_records_are_not_guessed_or_averaged(self):
        files=vectors();model=audit_yobj(files['psp-quad.yobj'])
        index=model['report']['mesh_reports'][0]['submeshes'][0]['index_ranges'][0]['start']
        vertex=model['report']['mesh_reports'][0]['vertex_buffer_start']
        for offset,fmt,value in ((index,'<H',65535),(vertex,'<f',.123)):
            changed=bytearray(files['psp-quad.yobj']);struct.pack_into(fmt,changed,offset,value)
            table=next(raw for s,raw in sections(files['psp-quad.pac']) if s['id']==9)
            with tempfile.TemporaryDirectory() as t:
                r=self.run_case(pac([(2,bytes(changed)),(9,table)]),Path(t))
                self.assertIsNone(r['repaired_pac'])
                self.assertTrue(r['before']['blocking_findings'])

    def test_new_reference_findings_reject_a_repair(self):
        files=vectors();table=next(raw for s,raw in sections(files['psp-quad.pac']) if s['id']==9)
        data=pac([(2,one_slot_model()),(9,table)])
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);reference=root/'Reference.pac';reference.write_bytes(b'ref')
            regression=dict(region='head',pose='jaw-18',kind='outlier',severity='review')
            with patch('model_qa.pipeline.run',side_effect=[dict(flags=[]),dict(flags=[regression])]):
                r=self.run_case(data,root,reference=reference)
            self.assertIsNone(r['repaired_pac'])
            self.assertFalse(r['reference_qa']['regression_check_passed'])
            self.assertFalse((root/'qa/candidate-for-qa.pac').exists())

    def test_repair_never_exceeds_configured_serialized_budget(self):
        files=vectors();table=next(raw for s,raw in sections(files['psp-quad.pac']) if s['id']==9)
        data=pac([(2,one_slot_model()),(9,table)])
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            # Force an additional allocation page; input itself still fits.
            from desktop.skinning import apply_single_slot_compatibility
            def too_large(raw,**kwargs):
                candidate,evidence=apply_single_slot_compatibility(raw,max_bytes=148000)
                return candidate+bytes(2048),evidence
            with patch('desktop.skinning.apply_single_slot_compatibility',side_effect=too_large):
                r=self.run_case(data,root,max_bytes=len(data))
            self.assertIsNone(r['repaired_pac']);self.assertTrue(r['after']['blocking_findings'])
            self.assertIn('withheld',r['status'])

if __name__=='__main__':unittest.main()
