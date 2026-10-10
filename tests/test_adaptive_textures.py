import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from desktop.core import Request,validate_pac,textures
from desktop.texture_optimizer.analysis import analyze,measure,occupied
from desktop.texture_optimizer.candidates import encode,generate,read_gim,write_gim,dimensions
from desktop.texture_optimizer.allocator import allocate
from desktop.texture_optimizer.pac import optimize_pac
from tools.generate_conformance_fixtures import vectors
from tools.psp_mesh_merge_trial import sections


def image(w=64,h=64):
    y,x=np.indices((h,w));a=np.empty((h,w,4),np.uint8)
    a[:,:,:3]=np.stack(((x*13+y*7)%256,(x*5+y*19)%256,(x*17+y*3)%256),2);a[:,:,3]=255
    return a


def choices(costs,losses):
    return [dict(entry=dict(serialized_bytes=c,metrics=dict(perceptual_loss=l))) for c,l in zip(costs,losses)]


class AdaptiveTextureTests(unittest.TestCase):
    def test_default_request_is_off(self):
        self.assertFalse(Request('a','b').adaptive_textures)
        with self.assertRaises(ValueError):Request('a','b',adaptive_textures='true').validate()

    def test_resolution_ceiling_rejects_upscale(self):
        with self.assertRaisesRegex(ValueError,'ceiling'):encode(image(32,32),(64,64),8,256)

    def test_palette_ceiling_actual_usage_not_declared_capacity(self):
        a=np.tile(np.array([[[1,2,3,255],[200,100,30,255]]],np.uint8),(32,16,1))
        row=encode(a,(32,32),8,256)
        self.assertEqual(row['entry']['requested_useful_colors'],2)
        self.assertEqual(row['entry']['used_palette_colors'],2)
        self.assertTrue(row['entry']['fully_preserved'])
        self.assertEqual(row['entry']['palette_entries'],256) # immutable storage overhead

    def test_resize_does_not_invent_more_useful_colors(self):
        a=np.zeros((64,64,4),np.uint8);a[:,:,3]=255;a[::2,::2,:3]=255
        row=encode(a,(32,32),8,256)
        self.assertLessEqual(row['entry']['used_palette_colors'],2)

    def test_rectangular_uniform_candidates(self):
        sizes=dimensions(128,64)
        self.assertIn((128,64),sizes);self.assertIn((64,32),sizes)
        self.assertTrue(all(w==h*2 for w,h in sizes))

    def test_no_generic_hardware_512_candidates(self):
        self.assertNotIn((512,512),dimensions(512,512))

    def test_narrow_padding_without_upscaling(self):
        a=np.zeros((8,8,4),np.uint8);a[:,:,3]=255
        row=encode(a,(8,8),4,16);p,c=read_gim(row['raw'])
        self.assertEqual(p.shape,(8,8));self.assertEqual(len(row['raw']),400)
        np.testing.assert_array_equal(c[p],a)

    def test_padded_decoder_rejects_bad_length(self):
        row=encode(image(32,32),(32,32),4,16)
        with self.assertRaises(ValueError):read_gim(row['raw'][:-1])

    def test_indexed8_unobserved_layout_is_not_generated(self):
        with self.assertRaisesRegex(ValueError,'not observed'):encode(image(256,256),(256,256),8,256)

    def test_gim_end_pointer_is_checked(self):
        import struct
        row=encode(image(32,32),(32,32),4,16);raw=bytearray(row['raw'])
        struct.pack_into('<I',raw,96,123)
        with self.assertRaisesRegex(ValueError,'pointer'):read_gim(raw)

    def test_unobserved_exact_incumbent_is_retained_not_regenerated(self):
        from experiments.texture_quality.frozen import FrozenPac
        from tools.texture_convert import read_gim as legacy_read,write_gim8
        f=vectors();p,c=legacy_read(f['skin-t4.gim']);p=np.resize(p,(16,32)).astype(np.uint8)
        palette=np.zeros((256,4),np.uint8);palette[:16]=c
        palette[int(p[0,0]),3]=0 # cutout alpha makes source-sized retention mandatory
        baseline,_=FrozenPac(f['psp-quad.pac']).build({'skin':write_gim8(p,palette)})
        source=palette[p]
        with tempfile.TemporaryDirectory() as t:
            data,r=optimize_pac(baseline,[(0,'skin',b'',source,{})],t)
            selected=r['textures'][0]['selected_configuration']
            self.assertEqual((selected['width'],selected['height']),(32,16))
            self.assertFalse(selected['native_corpus_layout_observed'])

    def test_alpha_exact_visible_rgb_and_transparent_padding(self):
        a=np.zeros((32,32,4),np.uint8);a[8:24,8:24]=[70,10,90,127];a[12:20,12:20]=[90,30,10,255]
        a[:8,:,:3]=image(32,8)[:,:,:3] # invisible colors do not require palette capacity
        row=encode(a,(32,32),8,256);p,c=read_gim(row['raw']);b=c[p]
        np.testing.assert_array_equal(b[:,:,3],a[:,:,3])
        np.testing.assert_array_equal(b[a[:,:,3]>0],a[a[:,:,3]>0])
        self.assertLessEqual(row['entry']['used_palette_colors'],3)
        with self.assertRaisesRegex(ValueError,'Alpha'):encode(a,(16,16),4,16)

    def test_alpha_preserved_independently_of_rgb_quantization(self):
        a=image(32,32);a[:,:,3]=127
        row=encode(a,(32,32),8,256);p,c=read_gim(row['raw'])
        np.testing.assert_array_equal(c[p][:,:,3],a[:,:,3])
        self.assertLessEqual(row['entry']['used_palette_colors'],256)

    def test_near_opaque_alpha_is_reported_and_never_becomes_cutout(self):
        a=image(32,32);a[:,:,3]=224+np.arange(32,dtype=np.uint8)[None,:]
        row=encode(a,(16,16),4,16);p,c=read_gim(row['raw'])
        self.assertTrue((c[p][:,:,3]>=128).all())
        self.assertTrue(set(np.unique(c[p][:,:,3]))<=set(np.unique(a[:,:,3])))
        self.assertFalse(row['entry']['metrics']['alpha_exact'])
        self.assertGreater(row['entry']['metrics']['alpha_mae'],0)

    def test_exact_legacy_generator_reference_hash(self):
        import hashlib,sys
        y,x=np.indices((64,64));a=np.stack(((x*5)%256,(y*7)%256,(x+y)%256,np.full_like(x,255)),2).astype(np.uint8)
        with tempfile.TemporaryDirectory() as t:
            _,gims=textures([(0,'test',b'',a,{})],dict(bones=[],meshes=[]),Path(t)/'textures',64)
            # Pillow's native resize/quantize path has different measured bytes
            # on Windows and Linux. Freeze each observed runtime, not a false
            # cross-platform identity requirement. Neither path was modified.
            expected='39cc683a26f077ccb40d0a612cffe5a15c568a05e2d69b716c88c9b45b7a9dcc' if sys.platform=='win32' else '5b1f23208af9cc1b66c2783bedb7d35ec3adf91dfb1892ee4051c29ae29e3d97'
            self.assertEqual(hashlib.sha256(gims[0]).hexdigest(),expected)

    def test_detail_coverage_tiny_vs_large(self):
        full=np.zeros((64,64,4),np.uint8);full[:,:,3]=255
        full[::2,:,:3]=255
        tiny=np.zeros_like(full);tiny[:,:,3]=255;tiny[20:28,20:28]=full[20:28,20:28]
        a,b=analyze(full),analyze(tiny)
        self.assertGreater(a['detail_coverage'],b['detail_coverage']*5)
        self.assertGreater(a['importance_score'],b['importance_score'])

    def test_alpha_padding_does_not_dilute_occupied_detail(self):
        a=np.zeros((64,64,4),np.uint8);a[16:48,16:48]=[0,0,0,255];a[16:48:2,16:48,:3]=255
        self.assertEqual(analyze(a)['occupied_fraction'],.25)
        self.assertGreater(analyze(a)['detail_coverage'],.7)

    def test_uv_unused_pixels_excluded(self):
        mask=np.zeros((64,64),bool);mask[:16,:16]=True
        self.assertAlmostEqual(analyze(image(),mask)['occupied_fraction'],1/16)

    def test_monochrome_detail_outranks_many_color_smooth_gradient(self):
        mono=np.zeros((64,64,4),np.uint8);mono[:,:,3]=255;mono[:,::2,:3]=255
        gradient=np.zeros_like(mono);gradient[:,:,3]=255;gradient[:,:,:3]=np.arange(64,dtype=np.uint8)[None,:,None]*4
        self.assertGreater(analyze(mono)['detail_score'],analyze(gradient)['detail_score'])
        self.assertGreater(analyze(mono)['reduction_sensitivity'],analyze(gradient)['reduction_sensitivity'])

    def test_solid_texture_has_no_detail(self):
        a=np.full((64,64,4),255,np.uint8)
        self.assertEqual(analyze(a)['detail_score'],0)
        self.assertEqual(analyze(a)['detail_coverage'],0)

    def test_identical_quality_is_one(self):
        a=image();m=measure(a,a)
        self.assertEqual(m['quality_score'],1)
        self.assertAlmostEqual(m['luminance_ssim'],1)

    def test_scoring_and_encoding_deterministic(self):
        a=image();self.assertEqual(analyze(a),analyze(a))
        self.assertEqual(encode(a,(32,32),8,256),encode(a,(32,32),8,256))

    def test_candidate_ceiling_and_material_immutability(self):
        a=image();analysis=dict(analyze(a),mask=occupied(a))
        rows,rejected=generate(a,analysis,4)
        self.assertTrue(rows)
        for row in rows:
            e=row['entry'];self.assertLessEqual(e['width'],64);self.assertLessEqual(e['height'],64)
            self.assertEqual(e['bits'],4);self.assertLessEqual(e['used_palette_colors'],16)
        self.assertTrue(any('immutable' in r['reason'] for r in rejected))

    def test_safe_minima_then_value_per_byte(self):
        rows=[choices([10,20,90],[.8,.3,.2]),choices([10,20],[.6,.5])]
        def build(s):
            cost=sum(r[i]['entry']['serialized_bytes'] for r,i in zip(rows,s))
            return bytes(cost),dict(pac_bytes=cost,pixel_palette_bytes=cost)
        _,selected,r=allocate(rows,[1.,1.],build,30,100)
        self.assertEqual(selected,(1,0));self.assertEqual(r['pac_bytes'],30)
        self.assertTrue(any(x['reason']=='Actual PAC size exceeds target' for x in r['rejected_upgrades']))

    def test_actual_size_not_theoretical_cost(self):
        rows=[choices([10,20],[.8,.1])]
        def build(s):return b'',dict(pac_bytes=10 if s[0]==0 else 99,pixel_palette_bytes=10)
        _,s,r=allocate(rows,[1],build,50,100)
        self.assertEqual(s,(0,));self.assertEqual(r['pac_bytes'],10)

    def test_final_size_recovery_with_compression_inversion(self):
        rows=[choices([10,20],[.8,.1])]
        def build(s):return b'',dict(pac_bytes=99 if s[0]==0 else 40,pixel_palette_bytes=10)
        _,s,r=allocate(rows,[1],build,50,100)
        self.assertEqual(s,(1,));self.assertEqual(r['decisions'][0]['action'],'serialized-budget-recovery')

    def test_budget_exhaustion_never_exports_oversized(self):
        rows=[choices([10],[.2])]
        def build(s):return b'oversized',dict(pac_bytes=100,pixel_palette_bytes=10)
        with self.assertRaisesRegex(ValueError,'withheld'):allocate(rows,[1],build,50,100)

    def test_pixel_memory_envelope_separate_from_pac(self):
        rows=[choices([10,20],[.8,.1])]
        def build(s):return b'',dict(pac_bytes=10,pixel_palette_bytes=10 if s[0]==0 else 100)
        _,s,_=allocate(rows,[1],build,50,20);self.assertEqual(s,(0,))

    def test_pac_only_texture_section_changes_and_report(self):
        fixture=vectors()['psp-quad.pac'];source=np.full((32,32,4),[180,25,35,255],np.uint8)
        decoded=[(0,'skin',b'',source,dict(declared_palette=256))]
        with tempfile.TemporaryDirectory() as temp:
            output,report=optimize_pac(fixture,decoded,temp)
            before={s['id']:s['sha256'] for s,r in sections(fixture)}
            after={s['id']:s['sha256'] for s,r in sections(output)}
            for i in before:
                if i!=9:self.assertEqual(before[i],after[i])
            validate_pac(output,gim_reader=read_gim)
            self.assertEqual(report['structural_validation'],'passed')
            self.assertTrue((Path(temp)/'report.html').is_file())
            self.assertLessEqual(report['pac_bytes'],148000)

    def test_legacy_method_has_no_adaptive_dependency(self):
        import inspect
        self.assertNotIn('texture_optimizer',inspect.getsource(textures))

    def test_retained_table_exception_is_explicit_and_lossless(self):
        from tools.pac_repack import rewrite_sections,texture_table
        from tools.yukes_bpe import compress
        f=vectors();table=texture_table(['blood'],[f['skin-t4.gim']])
        base=rewrite_sections(f['psp-quad.pac'],{},additions={8:table})
        converted=rewrite_sections(base,{8:compress(table)})
        with self.assertRaisesRegex(ValueError,'Unrelated'):validate_pac(converted,base)
        validate_pac(converted,base,lossless_texture_sections=[8])
        changed=rewrite_sections(base,{8:compress(table+b'extra')})
        with self.assertRaisesRegex(ValueError,'decoded'):validate_pac(changed,base,lossless_texture_sections=[8])


if __name__=='__main__':unittest.main()
