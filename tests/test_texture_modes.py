import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from desktop.core import Request,validate_pac
from desktop.texture_modes import MODES,downgrade_size,downgrade_texture,downgrade_pac
from desktop.texture_optimizer.candidates import read_gim,write_gim
from tools.generate_conformance_fixtures import vectors
from tools.pac_repack import texture_table,replace_sections
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress


class TextureModeTests(unittest.TestCase):
    def test_default_and_legacy_jobs_remain_default(self):
        self.assertEqual(MODES,('Default','ATO','Priority Selection','Downgrade'))
        self.assertEqual(Request('a','b').texture_mode,'')
        self.assertFalse(Request('a','b').use_adaptive)
        self.assertTrue(Request('a','b',adaptive_textures=True).use_adaptive)
        self.assertTrue(Request('a','b',texture_mode='ATO').use_adaptive)

    def test_modes_are_exclusive_and_steps_validated(self):
        for kwargs in (dict(texture_mode='bogus'),dict(texture_mode='Default',adaptive_textures=True),
                       dict(texture_mode='Default',downgrade_steps=1),dict(texture_mode='Downgrade'),
                       dict(texture_mode='ATO',priority_textures=['a']),dict(downgrade_steps=True),
                       dict(downgrade_steps=4),dict(downgrade_steps=1,adaptive_textures=True)):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):Request('a','b',**kwargs).validate()

    def test_three_source_steps_and_minimum(self):
        self.assertEqual([downgrade_size(512,512,i) for i in (1,2,3)],[(256,256),(128,128),(64,64)])
        self.assertEqual([downgrade_size(256,256,i) for i in (1,2,3)],[(128,128),(64,64),(64,64)])
        self.assertEqual(downgrade_size(128,128,3),(64,64))
        self.assertEqual(downgrade_size(64,64,3),(64,64))
        self.assertEqual(downgrade_size(32,32,3),(32,32))
        for steps in (0,4,True,'1'):
            with self.assertRaises(ValueError):downgrade_size(128,128,steps)

    def test_rectangles_preserve_aspect_and_no_upscale(self):
        self.assertEqual(downgrade_size(512,256,1),(256,128))
        self.assertEqual(downgrade_size(512,256,3),(64,32))
        self.assertEqual(downgrade_size(64,128,3),(32,64))
        self.assertEqual(downgrade_size(128,32,1),(64,16))

    def test_reduces_default_baseline_preserving_palette(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim'])
        p=np.resize(p,(128,128));baseline=write_gim(p,c,4)
        source=np.resize(c[p],(256,256,4))
        raw,r=downgrade_texture(source,baseline,1)
        self.assertEqual(r['source_dimensions'],[256,256])
        self.assertEqual(r['baseline_dimensions'],[128,128])
        self.assertEqual(r['selected_dimensions'],[64,64])
        self.assertEqual(r['bits'],4)
        np.testing.assert_array_equal(read_gim(raw)[1],c)
        self.assertEqual(read_gim(raw)[0].shape,(64,64))

    def test_small_default_maps_stay_exact_without_upscaling(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim'])
        source=np.resize(c[p],(128,128,4))
        raw,r=downgrade_texture(source,f['skin-t4.gim'],3)
        self.assertEqual(raw,f['skin-t4.gim'])
        self.assertEqual(r['selected_dimensions'],list(p.shape[1::-1]))
        self.assertEqual(r['actual_steps'],0)

    def test_cutout_alpha_sampled_exact_without_new_levels(self):
        p=np.zeros((128,128),np.uint8);p[::2]=1;p[:,::4]=2
        c=np.zeros((256,4),np.uint8);c[0]=[40,50,60,0];c[1]=[120,130,140,64];c[2]=[90,100,110,255]
        baseline=write_gim(p,c,8)
        raw,r=downgrade_texture(c[p],baseline,1)
        from PIL import Image
        expected=np.asarray(Image.fromarray(c[p]).resize((64,64),Image.Resampling.NEAREST))
        np.testing.assert_array_equal(read_gim(raw)[1][read_gim(raw)[0]],expected)
        self.assertEqual(r['bits'],8)

    def test_unsupported_native_format_pair_is_not_invented(self):
        p=np.zeros((32,256),np.uint8);c=np.zeros((16,4),np.uint8);c[:,3]=255
        source=c[p]
        with self.assertRaisesRegex(ValueError,'whitelist'):
            downgrade_texture(source,write_gim(p,c,4),3)  # 64x8 T4 not observed

    def baseline(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim'])
        p=np.resize(p,(64,64));rgba=c[p]
        baseline=replace_sections(f['psp-quad.pac'],{9:compress(texture_table(['skin'],[write_gim(p,c,4)],gim_reader=read_gim))})
        return baseline,rgba

    def test_full_pac_preserves_model_and_all_other_payloads(self):
        baseline,source=self.baseline()
        with tempfile.TemporaryDirectory() as t:
            data,r=downgrade_pac(baseline,[(0,'skin',b'',source,{})],t,steps=3)
            validate_pac(data,gim_reader=read_gim)
            before={s['id']:raw for s,raw in sections(baseline)}
            after={s['id']:raw for s,raw in sections(data)}
            for i in before:
                if i!=9:self.assertEqual(before[i],after[i])
            self.assertTrue(r['export_eligible']);self.assertTrue(r['unchanged_non_texture_payloads'])
            self.assertEqual(r['pixel_palette_bytes'],r['pixel_palette_budget'])
            self.assertTrue((Path(t)/'report.html').is_file())
            self.assertLessEqual(len(data),148000)

    def test_size_failure_keeps_floor_and_does_not_write_pac(self):
        baseline,source=self.baseline()
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'64-pixel floor'):
                downgrade_pac(baseline,[(0,'skin',b'',source,{})],t,steps=3,target=1)
            r=json.loads((Path(t)/'failure-report.json').read_text())
            self.assertFalse(r['export_eligible']);self.assertEqual(r['textures'][0]['selected_dimensions'],[64,64])
            self.assertFalse(list(Path(t).glob('*.pac')))

    def test_texture_allocation_cannot_grow_by_downgrading(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim']);p=np.resize(p,(128,128));source=c[p]
        baseline=replace_sections(f['psp-quad.pac'],{9:compress(texture_table(['skin'],[write_gim(p,c,4)],gim_reader=read_gim))})
        with tempfile.TemporaryDirectory() as t:
            data,r=downgrade_pac(baseline,[(0,'skin',b'',source,{})],t,steps=3)
            self.assertTrue(r['pac_budget_pass']);self.assertTrue(r['pixel_budget_pass'])
            self.assertLess(r['pixel_palette_bytes'],r['pixel_palette_budget'])

    def test_deterministic_serialized_result(self):
        baseline,source=self.baseline()
        with tempfile.TemporaryDirectory() as t:
            a,r=downgrade_pac(baseline,[(0,'skin',b'',source,{})],Path(t)/'a',steps=1)
            b,s=downgrade_pac(baseline,[(0,'skin',b'',source,{})],Path(t)/'b',steps=1)
            self.assertEqual(a,b);self.assertEqual(r,s)


if __name__=='__main__':unittest.main()
