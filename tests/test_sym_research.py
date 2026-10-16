"""Generated controls prove diagnostics, not native SYM compatibility."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tools.sym_research import Limits, probe, tim2_headers
from tools.yukes_bpe import compress
from tests.test_hctp_read import sample as hctp_sample
from tests.test_ps2_textures import rtx


def pac(items):
    result=b'PAC '+struct.pack('<I',len(items));offset=0
    for sid,data in items:
        result+=struct.pack('<H',sid)+offset.to_bytes(3,'little')+len(data).to_bytes(3,'little');offset+=len(data)
    return result+b''.join(d for _,d in items)


def tim2():
    header=bytearray(64);header[:4]=b'TIM2';struct.pack_into('<BBH',header,4,4,0,1)
    image=bytes(16);palette=bytes(64)
    struct.pack_into('<IIIHH4BHH',header,16,48+len(image)+len(palette),len(palette),len(image),48,16,0,1,3,4,8,4)
    return bytes(header)+image+palette


class SymResearchTests(unittest.TestCase):
    def test_hctp_contract_passing_does_not_enable_or_identify_sym(self):
        data=bytes(hctp_sample());r=probe(data,declared_game='sym')
        self.assertTrue(r['nodes'][0]['layout_probes']['hctp_weighted']['passed'])
        self.assertEqual(r['verified_source_game'],'UNKNOWN');self.assertFalse(r['conversion_supported'])
        from desktop.adapters import adapter
        with self.assertRaisesRegex(ValueError,'not supported'):adapter('sym')

    def test_unknown_wrapper_signature_is_not_decoded_by_carving(self):
        r=probe(b'UNKNOWN!'+bytes(hctp_sample()))
        self.assertEqual(len(r['nodes']),1);self.assertEqual(r['nodes'][0]['kind'],'UNKNOWN')
        self.assertIn(dict(signature='YOBJ',offset=8),r['signature_hits'])
        self.assertNotIn('layout_probes',r['nodes'][0])

    def test_pac_nested_models_and_bpe_are_all_inventoried(self):
        raw=bytes(hctp_sample());data=pac([(2,compress(raw)),(6,raw),(7,pac([(2,raw)]))])
        r=probe(data);models=[n for n in r['nodes'] if n['kind']=='YOBJ']
        self.assertEqual(len(models),3);self.assertIsNone(models[0]['file_offset'])
        self.assertIsInstance(models[1]['file_offset'],int);self.assertFalse(r['findings'])

    def test_duplicate_section_ids_remain_visible(self):
        r=probe(pac([(2,b'abcd'),(2,b'efgh')]))
        self.assertTrue(r['nodes'][0]['duplicate_section_ids']);self.assertEqual(len(r['nodes']),3)

    def test_pac_overlap_is_reported(self):
        data=bytearray(pac([(2,b'abcd'),(9,b'efgh')]));data[18:21]=bytes(3)
        r=probe(bytes(data));self.assertIn('Overlapping',r['nodes'][0]['probe_error'])

    def test_bpe_expansion_budget_and_depth_are_enforced(self):
        r=probe(compress(bytes(hctp_sample())),limits=replace(Limits(),max_expanded=10))
        self.assertIn('probe_error',r['nodes'][0]);self.assertEqual(r['resources']['expanded_bytes'],0)
        data=pac([(2,pac([(2,pac([(2,b'abcd')]))]))])
        r=probe(data,limits=replace(Limits(),max_depth=1))
        self.assertEqual(len(r['nodes']),2);self.assertTrue(r['findings'])

    def test_node_limit_reports_incomplete_inventory(self):
        r=probe(pac([(2,b'abcd'),(8,b'data')]),limits=replace(Limits(),max_nodes=2))
        self.assertLessEqual(r['resources']['nodes'],2);self.assertTrue(r['findings'])

    def test_oversized_tables_fail_before_allocating_entries(self):
        r=probe(b'PAC '+struct.pack('<I',1000000))
        self.assertIn('research node limit',r['nodes'][0]['probe_error'])
        r=probe(struct.pack('<4I',1000000,0x100,0,16))
        self.assertIn('research node limit',r['nodes'][0]['probe_error'])

    def test_unknown_dpac_is_not_misread_as_supported_pac(self):
        r=probe(b'DPAC'+bytes(64))
        self.assertEqual(r['nodes'][0]['kind'],'UNKNOWN');self.assertIn('not decoded',r['nodes'][0]['note'])

    def test_malformed_and_large_yobj_counts_are_bounded(self):
        self.assertIn('probe_error',probe(b'YOBJ')['nodes'][0])
        d=hctp_sample();struct.pack_into('<I',d,28,1000000)
        self.assertIn('count limits',probe(bytes(d))['nodes'][0]['probe_error'])
        d=hctp_sample();struct.pack_into('<I',d,112,1000000)
        self.assertIn('record',probe(bytes(d))['nodes'][0]['probe_error'])

    def test_corner_work_is_bounded_before_existing_reader(self):
        r=probe(bytes(hctp_sample()),limits=replace(Limits(),max_geometry_records=4))
        p=r['nodes'][0]['layout_probes']['hctp_weighted']
        self.assertFalse(p['passed']);self.assertIn('research limit',p['error'])

    def test_unsupported_skinning_keeps_raw_group_and_material_evidence(self):
        data=hctp_sample();struct.pack_into('<I',data,140,5)
        n=probe(bytes(data))['nodes'][0]
        self.assertFalse(n['layout_probes']['hctp_weighted']['passed'])
        fields=n['hctp_family_candidate_mesh_fields'][0]
        self.assertEqual(fields['groups'][0]['words'][1],5)
        self.assertEqual(len(fields['materials'][0]['raw_hex']),416)

    def test_low_variable_alpha_is_reported_and_preserved(self):
        colors=np.zeros((16,4),np.uint8);colors[:,3]=np.arange(16)*4
        data=bytearray(rtx(20,bytes([0x10,0x32])*64,colors.tobytes()));before=bytes(data)
        r=probe(data);n=r['nodes'][0]
        self.assertIn('alpha_review',n);self.assertFalse(n['decoded_alpha']['modified'])
        self.assertEqual(bytes(data),before);self.assertGreater(n['decoded_alpha']['intermediate_pixels'],0)

    def test_transparent_cutout_alpha_is_not_forced_opaque(self):
        colors=np.zeros((16,4),np.uint8);colors[1]=[30,50,80,128]
        r=probe(rtx(20,bytes([0x10])*128,colors.tobytes()));a=r['nodes'][0]['decoded_alpha']
        self.assertEqual(a['zero_pixels'],128);self.assertEqual(a['opaque_pixels'],128)
        self.assertNotIn('alpha_review',r['nodes'][0])

    def test_texture_budget_keeps_registers_without_decoding(self):
        data=rtx(20,bytes(128),bytes(64))
        n=probe(data,limits=replace(Limits(),max_texture_pixels=1))['nodes'][0]
        self.assertEqual(n['registers']['width'],32);self.assertIn('budget',n['probe_error'])
        self.assertNotIn('existing_rtx3_decoder',n)

    def test_tim2_headers_are_metadata_only(self):
        r=tim2_headers(tim2());self.assertFalse(r['pixels_decoded'])
        self.assertEqual(r['pictures'][0]['width'],8);self.assertEqual(r['pictures'][0]['declared_colors'],16)
        d=bytearray(tim2());d[5]=1
        with self.assertRaisesRegex(ValueError,'alignment variant'):tim2_headers(bytes(d))
        d=bytearray(tim2());struct.pack_into('<I',d,16,100000)
        with self.assertRaisesRegex(ValueError,'allocation'):tim2_headers(bytes(d))

    def test_named_texture_dependencies_and_offsets_are_reported(self):
        image=tim2();table=struct.pack('<4I',1,0x100,0,16)+b'face'.ljust(16,b'\0')+b'tm2\0'+struct.pack('<3I',len(image),48,0)+image
        r=probe(pac([(9,table)]));self.assertEqual([n['kind'] for n in r['nodes']],['PAC','named_texture_table','TIM2'])
        self.assertEqual(r['nodes'][-1]['file_offset'],64)

    def test_invalid_limits_and_input_budget_rejected(self):
        with self.assertRaisesRegex(ValueError,'size limit'):probe(b'ab',limits=replace(Limits(),max_input=1))
        with self.assertRaisesRegex(ValueError,'resource limits'):probe(b'ab',limits=replace(Limits(),max_nodes=0))

    def test_cli_deterministic_read_only_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'model.pac';output=root/'research.json';data=pac([(2,bytes(hctp_sample()))]);source.write_bytes(data)
            cmd=[sys.executable,'-m','tools.sym_research',str(source),'--output',str(output),'--declared-game','sym']
            first=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stderr)
            report=json.loads(output.read_text());self.assertEqual(report,json.loads(json.dumps(probe(data,declared_game='sym',source_name=source.name))))
            saved=output.read_bytes();again=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0);self.assertEqual(output.read_bytes(),saved);self.assertEqual(source.read_bytes(),data)


if __name__=='__main__':unittest.main()
