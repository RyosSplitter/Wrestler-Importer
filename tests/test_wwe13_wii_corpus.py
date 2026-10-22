"""Procedural boundary/layout regressions; no game-derived assets."""
import copy
import struct
import unittest
from unittest.mock import patch
import numpy as np
from tools.wwe13_wii_corpus import bundles,source_bundle,read_corpus_model
from tools.wwe13_wii_model import read_model
from tools.wwe13_adapter_trial import chart_atlas
from tools.wwe13_wii_trial import separate_eye_atlas
from tools.wwe13_normal_seams import mark_opposed
from tools.region_mesh import smooth_normals
from tests.test_wwe13_wii_model import fixture


def model(texture='Color'):
    return dict(bones=[dict(index=0,name='root',parent=-1,rotation=[0.,0.,0.],local_position=[0.,0.,0.])],
        textures=[texture],meshes=[dict(index=0,role='Body',source_material=0,bone_palette=[0],
        vertices=[dict(position=p,normal=[0.,0.,1.],uv=uv,color=[255]*4,weights=[1.])for p,uv in zip(
        [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],[[0.,0.],[1.,0.],[0.,1.]])],materials=[dict(texture_id=0,triangles=[[0,1,2]])])],
        source_decode_report={},triangle_count=1,vertex_count=3)


class CorpusTests(unittest.TestCase):
    def source(self,*,m=None,entries=None,sections=None,index=0):
        m=model()if m is None else m
        sections=sections or [dict(id=2,raw=b'DUMY'),dict(id=9,raw=b'x')]
        entries=entries or [dict(name='color',offset=0,size=1)]
        with patch('tools.wwe13_wii_corpus.bundles',return_value=[dict(offset=2048,sections=sections)]),\
             patch('tools.wwe13_wii_corpus.read_corpus_model',return_value=m),\
             patch('tools.wwe13_wii_corpus.parse_textures',return_value=entries),\
             patch('tools.wwe13_wii_corpus.decode_tpl',return_value=(np.full((32,32,4),255,np.uint8),{})):
            return source_bundle(b'EPK8',index)

    def test_body_only_case_binding_without_phantom_trans_texture(self):
        out,images,report=self.source()
        self.assertEqual(out['textures'],['wii_color']);self.assertEqual(len(images),1)
        self.assertEqual(out['triangle_count'],1);self.assertEqual(report['common_bind_maximum_difference'],0.)
    def test_case_collisions_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Case-ambiguous'):
            self.source(entries=[dict(name=n,offset=0,size=1)for n in ('color','Color')])
    def test_unknown_auxiliary_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed auxiliary'):
            self.source(sections=[dict(id=2,raw=b'DUMY'),dict(id=9,raw=b'x'),dict(id=20000,raw=b'DUMY')])
    def test_missing_used_texture_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'texture binding'):self.source(m=model('unknown'))
    def test_negative_variant_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Variant'):self.source(index=-1)
    def test_empty_or_non_epk8_input_rejected(self):
        for data in (b'',b'PAC '+bytes(4096),b'EPK8'+bytes(4096)):
            with self.assertRaises(ValueError):bundles(data)
    def test_aligned_discovery_retains_bounds(self):
        data=b'EPK8'+bytes(2044)+b'PACH'+bytes(2044)
        with patch('tools.wwe13_wii_corpus.read_pach',return_value=dict(end=4096,sections=[]))as read:
            self.assertEqual(len(bundles(data)),1);read.assert_called_once_with(data,2048)
    def test_nonsequential_draw_material_and_unused_record(self):
        raw,h=fixture();h['material_count']=2;struct.pack_into('>I',raw,28,0x300-8)
        struct.pack_into('>I',raw,0x324,0x220-8);raw[0x160]=1
        with patch('tools.wwe13_wii_model.read_model_header',return_value=h):m=read_model(bytes(24)+bytes(raw))
        self.assertEqual(m['meshes'][0]['source_material'],1)
        self.assertEqual(m['source_decode_report']['unused_material_records'][0]['index'],0)
    def test_eye_binding_appends_after_actual_texture_count(self):
        m=model();m['bones'][0]['name']='l_eye';before=copy.deepcopy(m)
        out,images=separate_eye_atlas(m,[np.full((32,32,4),255,np.uint8)])
        self.assertEqual(out['meshes'][0]['materials'][0]['texture_id'],1)
        self.assertEqual(len(out['textures']),len(images));self.assertEqual(m,before)
    def test_repeat_border_fallback_uses_exact_original_pixels(self):
        m=model('color');m['texture_count']=1
        y,x=np.indices((256,128));image=np.stack([x*2,y,(x+y)%256,np.full_like(x,255)],axis=2).astype(np.uint8)
        before=copy.deepcopy(m)
        with self.assertRaisesRegex(ValueError,'without upscaling'):chart_atlas(m,[image])
        out,images,report=chart_atlas(m,[image],repeat_safe=True)
        np.testing.assert_array_equal(images[0],image)
        for a,b in zip(m['meshes'][0]['vertices'],out['meshes'][0]['vertices']):
            self.assertEqual(a['uv'],b['uv']);self.assertEqual(a['position'],b['position'])
        self.assertEqual(m,before);self.assertFalse(report['geometry_moved'])
    def test_unreviewed_multipacket_count_rejected(self):
        payload=bytearray(256);struct.pack_into('>I',payload,32,0x70002);struct.pack_into('>I',payload,80,3)
        with self.assertRaisesRegex(ValueError,'multi-packet'):read_corpus_model(payload)
        struct.pack_into('>I',payload,32,0x70004);struct.pack_into('>I',payload,80,4)
        with self.assertRaisesRegex(ValueError,'multi-packet'):read_corpus_model(payload)
    def test_three_packets_retain_each_packet_and_reject_mismatched_version(self):
        payload=bytearray(320);struct.pack_into('>I',payload,32,0x70003);struct.pack_into('>I',payload,80,3)
        for i in range(3):payload[88+64*i:152+64*i]=bytes([5+i])*64
        before=bytes(payload)
        with patch('tools.wwe13_wii_corpus.read_model',side_effect=[model('color'),model('color'),model('trans')])as read:
            m=read_corpus_model(payload)
        self.assertEqual(bytes(payload),before)
        self.assertEqual(m['triangle_count'],3)
        self.assertEqual([x['source_packet']for x in m['meshes']],[0,1,2])
        self.assertEqual([x['materials'][0]['texture_id']for x in m['meshes']],[0,0,1])
        self.assertEqual(m['source_decode_report']['packet_header_offsets'],[64,128,192])
        for i,call in enumerate(read.call_args_list):
            view=call.args[0];self.assertEqual(view[88:152],before[88+64*i:152+64*i])
            self.assertEqual(view[152:],before[152:])
        struct.pack_into('>I',payload,80,2)
        with self.assertRaisesRegex(ValueError,'multi-packet'):read_corpus_model(payload)
        struct.pack_into('>I',payload,32,0x70001)
        with self.assertRaisesRegex(ValueError,'multi-packet'):read_corpus_model(payload)
    def test_opposed_authored_normal_seams_do_not_cancel(self):
        m=model();front=m['meshes'][0];front['vertices']=[dict(v,normal=[0.,0.,1.])for v in front['vertices']]
        back=copy.deepcopy(front);back['index']=1;back['materials'][0]['triangles']=[[2,1,0]]
        for v in back['vertices']:v['normal']=[0.,0.,-1.]
        m['meshes'].append(back);before=copy.deepcopy(m)
        with self.assertRaisesRegex(ValueError,'Degenerate'):smooth_normals(copy.deepcopy(m))
        mark_opposed(m);smooth_normals(m)
        self.assertGreater(m['opposed_normal_protection']['marked_corners'],0)
        for i,mesh in enumerate(m['meshes']):
            for v,w in zip(mesh['vertices'],before['meshes'][i]['vertices']):
                self.assertEqual(v['normal'],w['normal']);self.assertEqual(v['position'],w['position']);self.assertEqual(v['weights'],w['weights'])
    def test_two_packet_headers_are_private_and_materials_remapped(self):
        payload=bytearray(256);struct.pack_into('>I',payload,32,0x70002);struct.pack_into('>I',payload,80,2)
        payload[88:152]=bytes([5])*64;payload[152:216]=bytes([6])*64;before=bytes(payload)
        with patch('tools.wwe13_wii_corpus.read_model',side_effect=[model('color'),model('trans')])as read:
            m=read_corpus_model(payload)
        self.assertEqual(bytes(payload),before);self.assertEqual(m['triangle_count'],2)
        self.assertEqual([x['source_packet']for x in m['meshes']],[0,1])
        self.assertEqual(m['textures'],['color','trans'])
        for i,call in enumerate(read.call_args_list):
            view=call.args[0];self.assertEqual(view[88:152],before[88+64*i:152+64*i])
            self.assertEqual(view[216:],before[216:])


if __name__=='__main__':unittest.main()
