"""Generated contracts for the new Default policy and Legacy routing."""
from pathlib import Path
import tempfile
import unittest
import struct

import numpy as np

from desktop.core import Request
from desktop.default_textures import REFERENCE_PIXEL_BYTES, choose_priorities, upgrade
from desktop.texture_optimizer.candidates import read_gim, write_gim
from tools.generate_conformance_fixtures import vectors
from tools.pac_repack import replace_sections, texture_table
from tools.psp_mesh_merge_trial import sections
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_audit import audit_yobj
from tools.yukes_bpe import compress


def feature(name, score, coverage=.5, loss=.5, head=0.):
    return dict(name=name, attention_score=score, detail_coverage=coverage,
                fine_feature_loss=loss, head_fraction=head)


class DefaultTextureTests(unittest.TestCase):
    def test_routes_new_default_and_preserves_explicit_legacy_methods(self):
        for kwargs in ({},dict(texture_mode='Default'),dict(texture_mode='Downgrade',downgrade_steps=1),
                       dict(texture_mode='Priority Selection')):
            self.assertTrue(Request('a','b',**kwargs).default_texture_quality)
        for kwargs in (dict(texture_mode='Legacy'),dict(texture_mode='ATO'),dict(adaptive_textures=True),
                       dict(texture_mode='Maximum Downgrade'),dict(priority_textures=('skin',))):
            self.assertFalse(Request('a','b',**kwargs).default_texture_quality)

    def test_attention_prefers_dominant_lost_detail_not_texture_names(self):
        rows=[feature('arbitrary-a',1.2),feature('arbitrary-b',1.1),feature('arbitrary-c',.2),
              feature('head',4.,head=.9),feature('tiny',3.,coverage=.001),feature('already-clear',3.,loss=0.)]
        self.assertEqual(choose_priorities(rows),['arbitrary-a','arbitrary-b'])
        self.assertEqual(choose_priorities(list(reversed(rows))),['arbitrary-a','arbitrary-b'])
        self.assertEqual(len(choose_priorities([feature(str(i),1.) for i in range(8)])),3)

    def test_empty_detail_does_not_create_priorities(self):
        self.assertEqual(choose_priorities([feature('blank',0.,coverage=0.,loss=0.)]),[])

    def baseline(self):
        f=vectors()
        p,c=read_gim(f['skin-t4.gim']);c[:,3]=255
        # Match two source colors so this incumbent is a valid source-bounded seed.
        c[:,:3]=0;c[1,:3]=255;p[:]=0
        raw=write_gim(p,c,4)
        baseline=replace_sections(f['psp-quad.pac'],{9:compress(texture_table(['skin'],[raw],gim_reader=read_gim))})
        y,x=np.indices((64,64));rgba=np.zeros((64,64,4),np.uint8)
        rgba[:,:,:3]=(((x//2+y//2)%2)*255)[:,:,None];rgba[:,:,3]=255
        return baseline,[(0,'skin',b'',rgba,dict(format='synthetic'))]

    def test_reference_budget_can_restore_detail_without_model_changes(self):
        baseline,decoded=self.baseline()
        with tempfile.TemporaryDirectory() as td:
            a,r=upgrade(baseline,decoded,Path(td)/'quality')
            self.assertEqual(r['pixel_palette_budget'],REFERENCE_PIXEL_BYTES)
            self.assertIn('skin',r['default_policy']['chosen_priorities'])
            self.assertGreater(r['pixel_palette_bytes'],r['default_policy']['legacy_pixel_palette_bytes'])
            old={s['id']:raw for s,raw in sections(baseline)};new={s['id']:raw for s,raw in sections(a)}
            self.assertEqual(old[2],new[2]);self.assertLessEqual(len(a),148000)
            e=r['textures'][0]['selected_configuration']
            self.assertLessEqual(e['width'],64);self.assertLessEqual(e['height'],64)
            self.assertLessEqual(e['used_palette_colors'],2)

    def test_illegal_upscaled_legacy_seed_is_rebuilt_within_source_ceiling(self):
        baseline,decoded=self.baseline()
        # Source is 16x16, whereas the generated fixture incumbent is 32 pixels wide.
        decoded[0]=(0,'skin',b'',decoded[0][3][:16,:16],dict(format='synthetic'))
        with tempfile.TemporaryDirectory() as td:
            a,r=upgrade(baseline,decoded,Path(td)/'quality',priority_textures=('skin',))
            e=r['textures'][0]['selected_configuration']
            self.assertLessEqual(e['width'],16);self.assertLessEqual(e['height'],16)
            self.assertTrue(r['source_ceiling_seed_rebuilt'])

    def test_hard_pac_budget_still_withholds_when_allowance_is_larger(self):
        baseline,decoded=self.baseline()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):upgrade(baseline,decoded,Path(td)/'quality',target=1024)

    def test_unselected_narrow_source_can_restore_axis_without_donor_filter_blocking(self):
        baseline,decoded=self.baseline()
        raw=next(r for s,r in sections(baseline) if s['id']==2)
        model=audit_yobj(raw)
        model['texture_raw']=b'skin'.ljust(16,b'\0')+b'boot'.ljust(16,b'\0')
        model['texture_names']=['skin','boot']
        header=bytearray(model['header']);struct.pack_into('<I',header,32,2);model['header']=bytes(header)
        yobj=write_model(model,[[i] for i in range(len(model['meshes']))])
        p=np.zeros((16,32),np.uint8);c=np.zeros((16,4),np.uint8);c[:,3]=255
        c[0]=[40,50,60,255]
        boot=write_gim(p,c,4)
        old=next(r for s,r in sections(baseline) if s['id']==9)
        from tools.pac_inspect import parse_textures
        t=parse_textures(old)[0];skin=old[t['offset']:t['offset']+t['size']]
        baseline=replace_sections(baseline,{2:yobj,9:compress(texture_table(['skin','boot'],[skin,boot],gim_reader=read_gim))})
        source=np.full((32,16,4),[40,50,60,255],np.uint8)
        decoded.append((1,'boot',b'',source,dict(format='synthetic')))
        with tempfile.TemporaryDirectory() as td:
            a,r=upgrade(baseline,decoded,Path(td)/'quality',priority_textures=('skin',))
            boot=next(x for x in r['textures'] if x['name']=='boot')['selected_configuration']
            self.assertEqual((boot['width'],boot['height']),(16,32))
            self.assertTrue(r['source_ceiling_seed_rebuilt'])


if __name__=='__main__':
    unittest.main()
