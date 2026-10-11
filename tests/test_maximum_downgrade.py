"""Synthetic contracts: geometry frozen, alpha-safe rescue and hard budget."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from desktop.core import Request,validate_pac
from desktop.maximum_downgrade import candidates,fit_pac
from desktop.texture_optimizer.candidates import read_gim,write_gim,OBSERVED_DIMENSIONS,OBSERVED_T8_DIMENSIONS
from tools.generate_conformance_fixtures import vectors
from tools.pac_repack import replace_sections,texture_table
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress


class MaximumDowngradeTests(unittest.TestCase):
    def baseline(self,cutout=False):
        f=vectors();p,c=read_gim(f['skin-t4.gim'])
        p=np.random.default_rng(42).integers(0,16,(128,128),dtype=np.uint8)
        gim=write_gim(p,c,4)
        return replace_sections(f['psp-quad.pac'],{9:compress(texture_table(['skin'],[gim],gim_reader=read_gim))})

    def test_explicit_exclusive_mode(self):
        r=Request('a','b',texture_mode='Maximum Downgrade')
        self.assertTrue(r.maximum_downgrade);self.assertFalse(r.use_adaptive)
        for k in (dict(adaptive_textures=True),dict(downgrade_steps=1),dict(priority_textures=['skin'])):
            with self.assertRaises(ValueError):Request('a','b',texture_mode='Maximum Downgrade',**k).validate()

    def test_sub64_candidates_preserve_fixed_depth_and_no_upscale(self):
        p,c=read_gim(vectors()['skin-t4.gim']);p=np.resize(p,(64,64))
        c[:,3]=255
        rows=candidates(write_gim(p,c,4))
        self.assertTrue(any(r['dimensions']==[8,8] for r in rows))
        self.assertTrue(any(r['useful_colors']<16 for r in rows))
        for r in rows:
            self.assertEqual(r['bits'],4);self.assertEqual(r['palette_entries'],16)
            self.assertLessEqual(max(r['dimensions']),64)
            self.assertIn(tuple(r['dimensions']),OBSERVED_DIMENSIONS)

    def test_alpha_samples_and_cutout_survive(self):
        p=np.zeros((64,64),np.uint8);p[:,32:]=1;p[16:48,16:48]=2
        c=np.zeros((256,4),np.uint8);c[1]=[100,50,25,255];c[2]=[20,30,40,64]
        raw=write_gim(p,c,8);image=c[p]
        for r in candidates(raw):
            a,b=read_gim(r['raw']);expected=np.asarray(Image.fromarray(image[:,:,3]).resize(tuple(r['dimensions']),Image.Resampling.NEAREST))
            np.testing.assert_array_equal(b[a][:,:,3],expected)
            self.assertIn(tuple(r['dimensions']),OBSERVED_T8_DIMENSIONS)
            self.assertEqual(r['bits'],8)
            self.assertLessEqual(r['useful_colors'],3)
            self.assertTrue(np.any(expected<128));self.assertTrue(np.any(expected>=128))

    def test_already_fitting_pac_is_byte_identical(self):
        baseline=self.baseline()
        with tempfile.TemporaryDirectory() as t:
            data,r=fit_pac(baseline,t)
            self.assertEqual(data,baseline);self.assertEqual(r['changed_textures'],0)
            self.assertTrue(r['export_eligible'])

    def test_budget_rescue_and_exact_non_texture_payloads(self):
        baseline=self.baseline();target=len(baseline)-2048
        with tempfile.TemporaryDirectory() as t:
            data,r=fit_pac(baseline,t,target=target)
            validate_pac(data,max_bytes=target,gim_reader=read_gim)
            a={s['id']:(s['sha256'],raw) for s,raw in sections(baseline)}
            b={s['id']:(s['sha256'],raw) for s,raw in sections(data)}
            for i in a:
                if i!=9:self.assertEqual(a[i],b[i])
            self.assertLessEqual(len(data),target);self.assertGreater(r['changed_textures'],0)
            self.assertLessEqual(r['final_texture_pixel_palette_bytes'],r['texture_pixel_palette_budget'])
            self.assertTrue((Path(t)/'report.html').is_file())

    def test_impossible_budget_is_reported_without_pac_export(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'cannot fit'):fit_pac(self.baseline(),t,target=1)
            r=json.loads((Path(t)/'failure-report.json').read_text())
            self.assertFalse(r['export_eligible']);self.assertFalse(list(Path(t).glob('*.pac')))

    def test_deterministic_search(self):
        baseline=self.baseline();target=len(baseline)-2048
        with tempfile.TemporaryDirectory() as t:
            a,r=fit_pac(baseline,Path(t)/'a',target=target)
            b,s=fit_pac(baseline,Path(t)/'b',target=target)
            self.assertEqual(a,b);self.assertEqual(r,s)

    def test_cancellation_propagates(self):
        def cancel():raise RuntimeError('cancelled')
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(RuntimeError,'cancelled'):fit_pac(self.baseline(),t,target=1,cancel=cancel)


if __name__=='__main__':unittest.main()
