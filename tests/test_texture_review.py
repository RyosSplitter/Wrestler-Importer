import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from desktop.core import Request,validate_pac
from desktop.texture_review import validate_selection,source_previews,preview_image
from desktop.texture_optimizer.pac import optimize_pac
from desktop.texture_optimizer.candidates import read_gim
from tools.generate_conformance_fixtures import vectors
from tools.psp_mesh_merge_trial import sections
from tools.pac_inspect import parse_textures


class TextureReviewTests(unittest.TestCase):
    def test_request_defaults_and_limit(self):
        self.assertEqual(Request('a','b').priority_textures,())
        self.assertEqual(validate_selection(['a','b','c']),('a','b','c'))
        for names in (['a','b','c','d'],['a','a'],'a',[1],['']):
            with self.assertRaises(ValueError):validate_selection(names)
        with self.assertRaisesRegex(ValueError,'no longer'):validate_selection(['missing'],['present'])
        with self.assertRaisesRegex(ValueError,'SHA-256'):Request('a','b',priority_textures=['a']).validate()

    def test_source_previews_are_exact_and_use_generated_paths(self):
        rgba=np.zeros((16,32,4),np.uint8);rgba[4:8,4:8]=[50,60,70,127]
        with tempfile.TemporaryDirectory() as t:
            row=source_previews([(0,'../unsafe',b'',rgba,{'format':'synthetic'})],t)[0]
            self.assertEqual(Path(row['png']).parent,Path(t).resolve())
            np.testing.assert_array_equal(np.asarray(Image.open(row['png'])),rgba)

            self.assertEqual((row['width'],row['height'],row['useful_colors']),(32,16,1))
            self.assertTrue(row['has_alpha'])
            self.assertEqual(preview_image(row['png']).mode,'RGBA')
            np.testing.assert_array_equal(np.asarray(Image.open(row['png'])),rgba)

    def test_stale_preview_source_is_rejected(self):
        import hashlib
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source.pac';base=Path(t)/'base.pac'
            source.write_bytes(b'first');base.write_bytes(b'donor')
            fingerprint=hashlib.sha256(source.read_bytes()).hexdigest()
            request=Request(str(source),str(base),priority_textures=['skin'],texture_review_sha256=fingerprint)
            request.validate()
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed since'):request.validate()

    def test_empty_priorities_are_exact_existing_adaptive_behavior(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim']);decoded=[(0,'skin',b'',c[p],{})]
        with tempfile.TemporaryDirectory() as t:
            a,report=optimize_pac(f['psp-quad.pac'],decoded,Path(t)/'a')
            b,other=optimize_pac(f['psp-quad.pac'],decoded,Path(t)/'b',priority_textures=())
            self.assertEqual(a,b);self.assertEqual(report,other)

    def test_priorities_preserve_native_models_and_baseline_quality(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim']);rgba=c[p]
        source=rgba.copy()
        decoded=[(0,'skin',b'',source,{})]
        with tempfile.TemporaryDirectory() as t:
            a,r=optimize_pac(f['psp-quad.pac'],decoded,t,priority_textures=['skin'],freeze_unselected=True)
            validate_pac(a,gim_reader=read_gim)
            before={s['id']:raw for s,raw in sections(f['psp-quad.pac'])}
            after={s['id']:raw for s,raw in sections(a)}
            for i in before:
                if i!=9:self.assertEqual(before[i],after[i])
            self.assertLessEqual(len(a),148000)
            self.assertLessEqual(r['pixel_palette_bytes'],r['pixel_palette_budget'])
            row=r['textures'][0]
            self.assertTrue(row['manual_priority']);self.assertEqual(row['priority_multiplier'],8)
            self.assertGreaterEqual(row['priority_quality_improvement'],-1e-10)
            self.assertLessEqual(row['selected_configuration']['width'],source.shape[1])
            self.assertIn('priority_reduction_report',row)
            self.assertEqual(r['priority_textures'],['skin'])

    def test_unknown_priority_rejected_before_allocation(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'no longer'):
                optimize_pac(vectors()['psp-quad.pac'],[],t,priority_textures=['missing'])

    def test_final_size_cannot_be_bypassed_by_priority(self):
        f=vectors();p,c=read_gim(f['skin-t4.gim'])
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'budget'):
                optimize_pac(f['psp-quad.pac'],[(0,'skin',b'',c[p],{})],t,target=1,priority_textures=['skin'])
            self.assertTrue((Path(t)/'failure-report.json').is_file())

    def test_unselected_default_payloads_exact_with_multiple_textures(self):
        from unittest.mock import patch
        from tools import generate_conformance_fixtures as fixture
        from tools.pac_repack import texture_table
        from tools.yukes_bpe import compress
        class TwoTextures(fixture.Layout):
            def u32(self,address,value):
                super().u32(address,2 if address==32 and value==1 else value)
            def alloc(self,raw):
                if raw==b'skin'.ljust(16,b'\0'):raw+=b'other'.ljust(16,b'\0')
                return super().alloc(raw)
        f=vectors()
        with patch.object(fixture,'Layout',TwoTextures):model=fixture.model(True)
        table=texture_table(['skin','other'],[f['skin-t4.gim']]*2,gim_reader=read_gim)
        baseline=fixture.pac([(2,model),(9,compress(table))])
        p,c=read_gim(f['skin-t4.gim'])
        with tempfile.TemporaryDirectory() as t:
            a,r=optimize_pac(baseline,[(0,'skin',b'',c[p],{}),(1,'other',b'',c[p],{})],t,
                             priority_textures=['skin'],freeze_unselected=True)
            validate_pac(a,gim_reader=read_gim)
            final=next(raw for s,raw in sections(a) if s['id']==9)
            record=next(x for x in parse_textures(final) if x['name']=='other')
            self.assertEqual(final[record['offset']:record['offset']+record['size']],f['skin-t4.gim'])
            other=next(x for x in r['textures'] if x['name']=='other')
            self.assertFalse(other['manual_priority'])
            self.assertEqual(len(other['available_candidates']),1)


if __name__=='__main__':unittest.main()
