"""Synthetic conformance tests for the isolated texture research tools."""
import copy
import struct
import unittest

import numpy as np

from experiments.texture_quality.frozen import FrozenPac
from experiments.texture_quality.gim import read_native_gim
from experiments.texture_quality.inventory import gim_info
from experiments.texture_quality.metrics import compare,encode
from experiments.texture_quality.optimizer import propose,pareto
from experiments.texture_quality.trial import dimensions
from experiments.texture_quality.storage import lossless_table_trial
from tools.pac_repack import rewrite_sections,texture_table
from tools.generate_conformance_fixtures import vectors,pac
from tools.psp_mesh_merge_trial import sections
from tools.texture_convert import write_gim4,write_gim8,read_gim


class TextureExperimentTests(unittest.TestCase):
    def test_native_padded_decoder_matches_existing_subset_for_both_depths(self):
        for bits in (4,8):
            p=(np.arange(32*16,dtype=np.uint16).reshape(16,32)%(1<<bits)).astype(np.uint8)
            c=np.arange((1<<bits)*4,dtype=np.uint16).reshape(1<<bits,4).astype(np.uint8)
            raw=(write_gim4 if bits==4 else write_gim8)(p,c)
            a,b=read_native_gim(raw);np.testing.assert_array_equal(a,p);np.testing.assert_array_equal(b,c)
            self.assertTrue(gim_info(raw)['research_decoder_pass'])

    def test_logical_narrow_t4_width_crops_padded_physical_rows(self):
        p=(np.arange(32*8).reshape(8,32)%16).astype(np.uint8);c=np.zeros((16,4),dtype=np.uint8)
        raw=bytearray(write_gim4(p,c));struct.pack_into('<H',raw,72,8)
        a,b=read_native_gim(bytes(raw));np.testing.assert_array_equal(a,p[:,:8])
        info=gim_info(bytes(raw));self.assertEqual(info['image_allocation_bytes'],128)
        self.assertFalse(info['writer_subset_decodable']);self.assertTrue(info['research_decoder_pass'])

    def test_truncated_palette_and_out_of_bounds_image_are_rejected(self):
        raw=write_gim4(np.zeros((8,32),dtype=np.uint8),np.zeros((16,4),dtype=np.uint8))
        with self.assertRaises(ValueError):read_native_gim(raw[:-1])
        bad=bytearray(raw);struct.pack_into('<I',bad,92,0xfffffff0)
        with self.assertRaises(ValueError):gim_info(bytes(bad))

    def test_metric_identity_and_loss_of_small_pattern(self):
        rgba=np.zeros((32,32,4),dtype=np.uint8);rgba[:,:,3]=255;rgba[::2,::2,:3]=255
        same=compare(rgba,rgba);self.assertEqual(same['loss'],0);self.assertEqual(same['luminance_ssim'],1);self.assertIsNone(same['psnr_db'])
        blurred=np.full((8,8,4),127,dtype=np.uint8);blurred[:,:,3]=255
        bad=compare(rgba,blurred);self.assertGreater(bad['loss'],.1);self.assertLess(bad['luminance_ssim'],.2)

    def test_alpha_is_exact_and_never_silently_resized(self):
        rgba=np.zeros((8,32,4),dtype=np.uint8);rgba[:,::2]=[12,40,99,255];rgba[:,1::2]=[51,90,4,73]
        raw,back,row=encode(rgba,(32,8),4);np.testing.assert_array_equal(back,rgba)
        self.assertEqual(row['metrics']['alpha_mae'],0)
        with self.assertRaisesRegex(ValueError,'exact-resolution'):encode(rgba,(32,16),4)

    def test_palette_limit_preserves_source_or_rejects_alpha(self):
        rgba=np.zeros((16,32,4),dtype=np.uint8);rgba[:,:,0]=np.arange(32);rgba[:,:,1]=np.arange(16)[:,None];rgba[:,:,3]=127
        with self.assertRaisesRegex(ValueError,'palette'):encode(rgba,(32,16),8)

    def test_uniform_dimensions_preserve_aspect_even_at_writer_minimums(self):
        for w,h in ((128,128),(128,64),(32,16),(8,8),(64,256)):
            for bits in (4,8):
                for level in range(4):
                    a,b=dimensions(w,h,bits,level);self.assertEqual(a/b,w/h)
                    self.assertEqual(a%(32 if bits==4 else 16),0);self.assertEqual(b%8,0)
        with self.assertRaises(ValueError):dimensions(1024,1024,8)

    def test_texture_depth_change_preserves_every_geometric_byte(self):
        files=vectors();base=files['psp-quad.pac'];frozen=FrozenPac(base)
        p,c=read_gim(files['skin-t4.gim']);pal=np.zeros((256,4),dtype=np.uint8);pal[:16]=c
        result,report=frozen.build({'skin':write_gim8(p,pal)})
        self.assertTrue(report['export_eligible'])
        model=next(r for s,r in sections(result) if s['id']==2)
        before=next(r for s,r in sections(base) if s['id']==2)
        changed={i for i,(a,b) in enumerate(zip(before,model)) if a!=b}
        proof=report['model_proofs'][0];offset=proof['material_control_changes'][0]['offset']
        self.assertTrue(changed);self.assertTrue(changed<=set(range(offset,offset+4)))
        self.assertTrue(proof['geometric_buffers_weights_skeleton_topology_identical'])

    def test_structural_pass_does_not_override_pac_or_memory_budget(self):
        frozen=FrozenPac(vectors()['psp-quad.pac'],max_bytes=1024,max_texture_bytes=1)
        candidate,report=frozen.build(frozen.gims)
        self.assertFalse(report['pac_budget_pass']);self.assertFalse(report['texture_observed_envelope_pass']);self.assertFalse(report['export_eligible'])
        self.assertTrue(report['structural_validation'].startswith('PASS'))

    def test_beam_proposals_enforce_aspect_and_two_resource_constraints(self):
        def row(cost,mem,loss,aspect=True):return {'entry':dict(proposal_stored_cost=cost,pixel_palette_bytes=mem,weighted_loss=loss,aspect_ratio_preserved=aspect)}
        choices=[[row(1,1,9),row(2,2,1),row(1,1,0,False)],[row(1,1,9),row(4,4,0)]]
        results=propose(choices,4,4)
        self.assertTrue(results)
        for c,m,l,selection in results:self.assertLessEqual(c,4);self.assertLessEqual(m,4);self.assertNotEqual(selection[0],2)

    def test_legacy_distorted_option_cannot_eliminate_all_uniform_options(self):
        def row(cost,mem,loss,aspect,quantizer):return {'entry':dict(proposal_stored_cost=cost,pixel_palette_bytes=mem,weighted_loss=loss,aspect_ratio_preserved=aspect,quantizer=quantizer)}
        legacy=row(1,1,0,False,'Existing baseline');valid=row(2,2,0,True,'Exact');dominated=row(3,3,1,True,'Other')
        kept=pareto([legacy,valid,dominated]);self.assertIn(legacy,kept);self.assertIn(valid,kept);self.assertNotIn(dominated,kept)

    def test_lossless_texture_storage_preserves_all_decoded_sections(self):
        v=vectors();table=texture_table(['blood'],[v['skin-t4.gim']]);base=rewrite_sections(v['psp-quad.pac'],{},additions={8:table})
        frozen=FrozenPac(base);result,report=lossless_table_trial(frozen,frozen.gims)
        before=dict((s['id'],raw) for s,raw in sections(base));after=dict((s['id'],raw) for s,raw in sections(result))
        self.assertEqual(before,after);self.assertGreater(report['retained_table_lossless_storage']['stored_savings_bytes'],0)
        self.assertTrue(report['retained_table_lossless_storage']['baseline_geometry_model_and_rig_stored_bytes_preserved'])

    def test_unknown_section_eight_is_not_treated_as_a_texture_table(self):
        v=vectors();base=rewrite_sections(v['psp-quad.pac'],{},additions={8:b'JUDE'+bytes(20)})
        f=FrozenPac(base)
        with self.assertRaises(ValueError):lossless_table_trial(f,f.gims)


if __name__=='__main__':unittest.main()
