"""Independent binary/IR oracle for Q7/Q8, including the old twice-size bug."""
import copy
import struct
import unittest
from unittest.mock import patch
import numpy as np
from tests.test_wwe13_wii_model import fixture
from tools.wwe13_wii_model import read_model
from model_qa.wii_source_encoding import verify


class SourceEncodingTests(unittest.TestCase):
    def case(self,fraction=7):
        raw,header=fixture();raw[0x74]=fraction
        struct.pack_into('>I',raw,4,len(raw)-8);struct.pack_into('>I',raw,56,1)
        payload=bytes(24)+bytes(raw)
        with patch('tools.wwe13_wii_model.read_model_header',return_value=header):model=read_model(payload)
        for mesh in model['meshes']:mesh['source_section']=2
        return payload,model

    def audit(self,payload,model):
        with patch('model_qa.wii_source_encoding.bundles',return_value=[dict(sections=[dict(id=2,raw=b'DUMY'+payload[4:])])]):
            return verify(b'procedural source',0,model)

    def test_q7_and_q8_sources_verify_exactly(self):
        for fraction in (7,8):
            payload,m=self.case(fraction);before=copy.deepcopy(m)
            report=self.audit(payload,m)
            self.assertEqual(report['status'],'pass');self.assertEqual(report['packets'][0]['position_divisor'],2**fraction)
            self.assertEqual(report['packets'][0]['vertex_records_checked'],3);self.assertEqual(m,before)

    def test_old_hardcoded_divisor_bug_is_detected_before_reference_qa(self):
        payload,m=self.case(8)
        for mesh in m['meshes']:
            for v in mesh['vertices']:v['position']=(np.array(v['position'])*2).tolist()
        with self.assertRaisesRegex(ValueError,'position-scale mismatch.*Q8'):self.audit(payload,m)

    def test_unrelated_source_record_change_is_detected(self):
        payload,m=self.case();m['meshes'][0]['vertices'][0]['position'][0]+=.01
        with self.assertRaisesRegex(ValueError,'position-scale mismatch'):self.audit(payload,m)

    def test_out_of_range_vertex_and_packet_are_rejected(self):
        payload,m=self.case();m['meshes'][0]['vertices'][0]['source_position_index']=999
        with self.assertRaisesRegex(ValueError,'outside'):self.audit(payload,m)
        payload,m=self.case();m['meshes'][0]['source_packet']=1
        with self.assertRaisesRegex(ValueError,'no encoding audit packet'):self.audit(payload,m)

    def test_unrecognized_binary_point_is_rejected(self):
        payload,m=self.case();raw=bytearray(payload);raw[24+0x74]=9
        with self.assertRaisesRegex(ValueError,'Unobserved position fraction'):self.audit(bytes(raw),m)

    def test_unknown_packet_count_is_not_silently_ignored(self):
        payload,m=self.case();raw=bytearray(payload);struct.pack_into('>I',raw,24+56,3)
        with self.assertRaisesRegex(ValueError,'packet count'):self.audit(bytes(raw),m)

    def test_mixed_q7_q8_packets_use_their_own_fields(self):
        from tools.wwe13_wii_corpus import read_corpus_model
        raw,header=fixture();struct.pack_into('>I',raw,4,len(raw)-8)
        struct.pack_into('>I',raw,8,0x70002);struct.pack_into('>I',raw,56,2)
        raw[128:192]=raw[64:128];raw[128+52]=8
        header['bones']=[dict(index=i,name='bone'+str(i),parent=-1) for i in range(3)]
        payload=bytes(24)+bytes(raw);before=bytes(payload)
        with patch('tools.wwe13_wii_model.read_model_header',return_value=header):m=read_corpus_model(payload)
        for mesh in m['meshes']:mesh['source_section']=2
        self.assertEqual(payload,before)
        for a,b in zip(m['meshes'][0]['vertices'],m['meshes'][1]['vertices']):
            np.testing.assert_array_equal(np.array(a['position'])/2,b['position'])
            self.assertEqual(a['weights'],b['weights']);self.assertEqual(a['uv'],b['uv'])
        report=self.audit(payload,m)
        self.assertEqual([p['position_divisor']for p in report['packets']],[128,256])

    def test_cutout_leg_weights_are_preserved_by_full_retention_classification(self):
        from tools.wwe13_reduce_trial import classify
        bones=[dict(index=i,name=n,parent=-1,local_position=[0.,0.,0.],rotation=[0.,0.,0.]) for i,n in enumerate(('root','l_eye','r_eye','l_momo'))]
        m=dict(bones=bones,bone_count=4,meshes=[dict(index=0,role='Cutout',bone_palette=list(range(4)),
            vertices=[dict(position=p,normal=[0.,0.,1.],uv=[0.,0.],color=[255]*4,weights=[0.,0.,0.,1.]) for p in ([0.,0.,0.],[1.,0.,0.],[0.,1.,0.])],
            materials=[dict(texture_id=0,triangles=[[0,1,2]])])])
        out=classify(m,hand_weighted=True)
        self.assertEqual(out['meshes'][0]['region'],'Hair')  # historical full-retention profile label
        self.assertTrue(all(v['weights']==[0.,0.,0.,1.]for v in out['meshes'][0]['vertices']))


if __name__=='__main__':unittest.main()
