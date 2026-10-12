"""Independent fixtures and repository oracles for the standalone Noesis plugin."""
import importlib.util
from pathlib import Path
import struct
import unittest

import numpy as np
from tools.generate_conformance_fixtures import vectors
from tools.psp_mesh_audit import audit_yobj
from tools.yukes_bpe import compress
from desktop.texture_optimizer.candidates import write_gim, read_gim

spec=importlib.util.spec_from_file_location('wwe_psp_plugin',Path(__file__).resolve().parents[1]/'plugins/noesis/fmt_wwe_psp_yobj.py')
plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)


class NoesisPSPTests(unittest.TestCase):
    def test_vertices_uv_normals_weights_materials_and_strip_winding(self):
        raw=vectors()['psp-quad.yobj'];native=audit_yobj(raw);model=plugin.parse_yobj(raw)
        self.assertEqual(native['texture_names'],model['texture_names'])
        for a,b in zip(native['meshes'],model['meshes']):
            self.assertEqual(a['vertices'],b['vertices']);self.assertEqual(a['stride'],b['stride'])
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            for x,y in zip(a['materials'],b['materials']):
                self.assertEqual(x['triangles'],y['triangles']);self.assertEqual(x['strips'],list(map(list,y['strips'])))

    def test_ps2_layout_not_claimed(self):
        f=vectors();self.assertEqual(plugin.check_type(f['hctp-quad.yobj']),0)
        self.assertEqual(plugin.check_type(f['psp-quad.yobj']),1)
        self.assertEqual(plugin.check_type(b'YOBJ'),0)

    def test_compressed_model_and_pac_embedded_textures(self):
        f=vectors();models,tex=plugin.read_scene(f['psp-quad.pac'])
        self.assertEqual(len(models),1);self.assertIn('skin',tex)
        self.assertEqual(plugin.decompress(compress(f['psp-quad.yobj'])),f['psp-quad.yobj'])
        self.assertEqual(plugin.read_scene(compress(f['psp-quad.pac'])),(models,tex))

    def test_gim_pixel_exact_rectangular_narrow_and_transparent(self):
        for bits,size in [(4,(8,8)),(4,(16,32)),(4,(64,32)),(8,(32,8)),(8,(64,128))]:
            w,h=size;y,x=np.indices((h,w));indices=((x+y*7)%(1<<bits)).astype(np.uint8)
            palette=np.arange((1<<bits)*4,dtype=np.uint8).reshape(-1,4);palette[0]=0
            blob=write_gim(indices,palette,bits);width,height,rgba=plugin.decode_gim(blob)
            self.assertEqual((width,height),size);self.assertEqual(rgba,palette[indices].tobytes())

    def test_malformed_index_palette_pointer_and_bpe_rejected(self):
        f=vectors();raw=f['psp-quad.yobj'];a=audit_yobj(raw)
        bad=bytearray(raw);idx=a['report']['mesh_reports'][0]['submeshes'][0]['index_ranges'][0]['start']
        struct.pack_into('<H',bad,idx,65535)
        with self.assertRaisesRegex(ValueError,'Index'):plugin.parse_yobj(bytes(bad))
        bad=bytearray(raw);mesh=struct.unpack_from('<I',raw,36)[0]+8;pal=struct.unpack_from('<I',raw,mesh+8)[0]+8
        struct.pack_into('<I',bad,pal+16,0)
        with self.assertRaisesRegex(ValueError,'palette'):plugin.parse_yobj(bytes(bad))
        bad=bytearray(raw);struct.pack_into('<I',bad,36,len(raw)+64)
        with self.assertRaises(ValueError):plugin.parse_yobj(bytes(bad))
        for bad in [b'BPE ',compress(raw)[:-1],b'PAC '+struct.pack('<I',4097)]:
            self.assertEqual(plugin.check_type(bad),0)

    def test_multiple_yobj_sections_are_retained(self):
        from tools.generate_conformance_fixtures import pac
        f=vectors();raw=pac([(6,f['psp-quad.yobj']),(2,compress(f['psp-quad.yobj'])),(7,f['psp-quad.yobj'])])
        models,tex=plugin.read_scene(raw)
        self.assertEqual([section for section,m in models],[2,6,7])

    def test_ge_integer_and_rigid_layouts(self):
        raw=vectors()['psp-quad.yobj'];expected=plugin.parse_yobj(raw)
        mesh=expected['meshes'][0];start=struct.unpack_from('<I',raw,36)[0]+8
        cell=struct.unpack_from('<I',raw,start+24)[0]+8
        vp=struct.unpack_from('<I',raw,cell)[0]+8
        for flag,width,fmt,den in [(0x13ff,1,'B',128),(0x15ff,2,'H',32768),(0x11ff,0,'',1)]:
            data=bytearray(raw);struct.pack_into('<I',data,start+28,flag|((len(mesh['bone_palette'])-1)<<14) if width else flag)
            for j,v in enumerate(mesh['vertices']):
                weights=struct.pack('<'+fmt*len(v['weights']),*[round(w*den) for w in v['weights']]) if width else b''
                weights+=bytes((-len(weights))%4)
                attr=struct.pack('<2f4B6f',*v['uv'],*v['color'],*v['normal'],*v['position'])
                record=weights+attr;data[vp+j*len(record):vp+(j+1)*len(record)]=record
            parsed=plugin.parse_yobj(bytes(data))['meshes'][0]
            for a,b in zip(mesh['vertices'],parsed['vertices']):
                for k in ['position','normal','uv','color']:self.assertEqual(a[k],b[k])
                self.assertEqual(b['weights'],a['weights'] if width else [])

    def test_noesis_callback_uses_native_indices_embedded_images_and_rgba(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        captures=[];bindings={};result=[]
        class Texture:
            def __init__(self,name,w,h,rgba,pixel_type):self.name=name;self.rgba=rgba
        class Material:
            def __init__(self,name,texture):self.name=name
            def setAlphaTest(self,value):self.alpha_test=value
        class Model:
            def setModelMaterials(self,value):self.materials=value
        def bind(name):
            def fn(raw,*args):bindings[name]=raw
            return fn
        def commit(raw,typ,count,primitive,flag):captures.append((dict(bindings),raw,count))
        rapi=SimpleNamespace(rpgCreateContext=lambda:None,getDirForFilePath=lambda x:'',getInputName=lambda:'sample.pac',
            rpgBindPositionBuffer=bind('positions'),rpgBindNormalBuffer=bind('normals'),rpgBindUV1Buffer=bind('uv'),
            rpgBindColorBufferOfs=bind('colors'),rpgSetName=lambda x:None,rpgSetMaterial=lambda x:None,
            rpgCommitTriangles=commit,rpgClearBufferBinds=lambda:bindings.clear(),rpgConstructModel=lambda:Model())
        api=SimpleNamespace(optWasInvoked=lambda x:False,NOESISTEX_RGBA32=0,RPGEODATA_FLOAT=0,
            RPGEODATA_UBYTE=1,RPGEODATA_INT=2,RPGEO_TRIANGLE=3,logPopup=lambda:None)
        with patch.multiple(plugin,noesis=api,rapi=rapi,NoeTexture=Texture,NoeMaterial=Material,
                            NoeModelMaterials=lambda a,b:(a,b),create=True):
            self.assertEqual(plugin.load_model(vectors()['psp-quad.pac'],result),1)
        self.assertEqual(len(result),1);buffers,indices,count=captures[0]
        self.assertEqual(count,6)
        self.assertEqual(struct.unpack('<6I',indices),(0,1,2,1,3,2))
        source=plugin.parse_yobj(vectors()['psp-quad.yobj'])['meshes'][0]['vertices']
        self.assertEqual(buffers['uv'],b''.join(struct.pack('<2f',*v['uv']) for v in source))
        self.assertEqual(buffers['colors'],bytes(x for v in source for x in v['color']))
        self.assertEqual(buffers['positions'],b''.join(struct.pack('<3f',v['position'][0],v['position'][2],-v['position'][1]) for v in source))


if __name__=='__main__':unittest.main()
