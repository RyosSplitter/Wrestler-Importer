"""Independent budget functions test exchanges, not the PAC packer's own math."""
import unittest

from desktop.texture_optimizer.priorities import allocate_priorities


def row(cost,loss):
    return dict(entry=dict(serialized_bytes=cost,pixel_palette_bytes=cost,
                           metrics=dict(perceptual_loss=loss)))


class PriorityReallocationTests(unittest.TestCase):
    def allocate(self,choices,initial,priorities,weights=None,target=100):
        def build(selection):
            cost=sum(rows[i]['entry']['serialized_bytes'] for rows,i in zip(choices,selection))
            return bytes(selection),dict(pac_bytes=cost,pixel_palette_bytes=cost,
                                          texture_stored_bytes=cost)
        return allocate_priorities(choices,weights or [8 if j in priorities else 1 for j in range(len(choices))],
            build,target,target,initial,priorities)

    def test_donor_exchange_restores_selected_detail_at_full_budget(self):
        choices=[[row(10,.8),row(70,.05)],[row(90,.05),row(30,.2)]]
        payload,s,r=self.allocate(choices,[0,0],[0])
        self.assertEqual(s,(1,1));self.assertEqual(payload,bytes(s))
        self.assertEqual(r['pac_bytes'],100)
        self.assertGreater(r['decisions'][0]['net_weighted_quality_gain'],0)
        self.assertEqual(r['decisions'][0]['donor_changes'][0]['texture_index'],1)

    def test_selected_textures_never_fund_another_selection(self):
        choices=[[row(40,.1),row(80,0),row(10,.9)],
                 [row(60,.1),row(20,.8)]]
        _,s,r=self.allocate(choices,[0,0],[0,1])
        self.assertEqual(s,(0,0));self.assertTrue(r['rejected_upgrades'])

    def test_multiple_donors_and_deterministic_result(self):
        choices=[[row(10,.8),row(70,0)],
                 [row(45,0),row(15,.1)], [row(45,0),row(15,.1)]]
        a=self.allocate(choices,[0,0,0],[0]);b=self.allocate(choices,[0,0,0],[0])
        self.assertEqual(a,b);self.assertEqual(a[1],(1,1,1))

    def test_rejects_exchange_with_excessive_unselected_loss(self):
        choices=[[row(10,.05),row(70,0)],[row(90,0),row(30,1)]]
        _,s,r=self.allocate(choices,[0,0],[0])
        self.assertEqual(s,(0,0))
        self.assertEqual(r['rejected_upgrades'][0]['reason'],'Donor quality cost outweighs selected gain')

    def test_separate_pixel_budget_is_enforced_even_when_pac_fits(self):
        choices=[[row(10,.9),row(70,0)],[row(90,0),row(30,.1)]]
        def build(s):
            pixels=sum(rs[i]['entry']['pixel_palette_bytes'] for rs,i in zip(choices,s))
            return bytes(s),dict(pac_bytes=50,texture_stored_bytes=40,pixel_palette_bytes=pixels)
        _,s,r=allocate_priorities(choices,[8,1],build,100,100,[0,0],[0])
        self.assertEqual(s,(1,1));self.assertLessEqual(r['pixel_palette_bytes'],100)

    def test_serialized_padding_and_compression_override_estimates(self):
        choices=[[row(10,.8),row(70,0)],[row(90,0),row(30,.1)]]
        def build(s):
            return bytes(s),dict(pac_bytes=100 if s[0]==0 else 101,
                texture_stored_bytes=90 if s[0]==0 else 91,
                pixel_palette_bytes=sum(rs[i]['entry']['pixel_palette_bytes'] for rs,i in zip(choices,s)))
        _,s,r=allocate_priorities(choices,[8,1],build,100,100,[0,0],[0])
        self.assertEqual(s,(0,0));self.assertLessEqual(r['pac_bytes'],100)

    def test_cancel_propagates(self):
        def cancel():raise InterruptedError('cancel')
        with self.assertRaises(InterruptedError):
            allocate_priorities([[row(1,0)]],[8],lambda _:None,1,1,[0],[0],cancel)

    def test_real_gim_pac_reallocation_preserves_model_and_source_ceilings(self):
        import tempfile
        from unittest.mock import patch
        import numpy as np
        from PIL import Image
        from desktop.core import validate_pac
        from desktop.texture_optimizer.pac import optimize_pac
        from desktop.texture_optimizer.candidates import read_gim,write_gim
        from tools import generate_conformance_fixtures as fixture
        from tools.psp_mesh_merge_trial import sections
        from tools.pac_repack import texture_table
        from tools.yukes_bpe import compress
        class TwoTextures(fixture.Layout):
            def u32(self,address,value):
                super().u32(address,2 if address==32 and value==1 else value)
            def alloc(self,raw):
                if raw==b'skin'.ljust(16,b'\0'):raw+=b'other'.ljust(16,b'\0')
                return super().alloc(raw)
        palette=np.zeros((16,4),np.uint8);palette[:4]=[[0,100,70,255],[0,0,0,255],[180,250,40,255],[0,200,120,255]]
        y,x=np.indices((32,64));pattern=((x//3+y//5)%4).astype(np.uint8)
        original=palette[pattern]
        small=np.asarray(Image.fromarray(pattern).resize((8,8),Image.Resampling.NEAREST))
        y,x=np.indices((64,64));plain=((x//16+y//32)%4).astype(np.uint8)
        gims=[write_gim(small,palette,4),write_gim(plain,palette,4)]
        with patch.object(fixture,'Layout',TwoTextures):model=fixture.model(True)
        baseline=fixture.pac([(2,model),(9,compress(texture_table(['skin','other'],gims,gim_reader=read_gim)))])
        decoded=[(0,'skin',b'',original,{}),(1,'other',b'',palette[plain],{})]
        with tempfile.TemporaryDirectory() as folder:
            final,report=optimize_pac(baseline,decoded,folder,priority_textures=['skin'],rebalance_priorities=True)
            validate_pac(final,gim_reader=read_gim)
            a={s['id']:raw for s,raw in sections(baseline)};b={s['id']:raw for s,raw in sections(final)}
            self.assertEqual(a[2],b[2])
            self.assertLessEqual(report['pixel_palette_bytes'],report['pixel_palette_budget'])
            selected=report['textures'][0]
            self.assertGreater(selected['priority_quality_improvement'],0)
            self.assertLessEqual(selected['selected_configuration']['width'],64)
            self.assertLessEqual(selected['selected_configuration']['height'],32)
            self.assertLessEqual(selected['selected_configuration']['used_palette_colors'],4)
            self.assertLessEqual(len(final),148000)


if __name__=='__main__':unittest.main()
