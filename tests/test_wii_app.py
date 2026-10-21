"""Wii app boundary, source selection, texture contracts and export regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from desktop.adapters import adapter,FORMATS
from desktop.adapters.wwe13_wii import selected_index
from desktop.core import Request,run_job,Cancelled,digest
from desktop.storage import save_as
from desktop.texture_optimizer.candidates import read_gim,write_gim
from tools.psp_mesh_audit import audit_yobj
from tools.wwe13_texture_trial import allocate
from tools.wwe13_texture_format_trial import patch_regular_depths
from tools.psp_mesh_merge_trial import sections

FIXTURES=Path(__file__).parent/'fixtures/hctp_psp'
BASE=Path(__file__).parents[1]/'assets/Kurt-Angle-Ring.PAC'


class WiiAppTests(unittest.TestCase):
    def request(self,root,**kwargs):
        a,b=Path(root)/'source.pac',Path(root)/'base.pac'
        a.write_bytes(b'EPK8');b.write_bytes(b'PAC ')
        return Request(str(a),str(b),source_format='wwe13-wii',**kwargs)

    def test_explicit_platform_is_separate_from_ps2_and_x360(self):
        self.assertEqual(adapter('wwe13-wii').key,'wwe13-wii')
        self.assertNotEqual(type(adapter('wwe13-wii')),type(adapter('hctp')))
        self.assertTrue(next(f for f in FORMATS if f.key=='wwe13-wii').supported)
        for key in ('sym','svr','wwe13-x360'):
            with self.assertRaises(ValueError):adapter(key)

    def test_variant_selection_is_bounded_and_not_a_path(self):
        for value in ('','00','01'):self.assertEqual(selected_index(value,2),int(value or 0))
        for value in ('-1','99','001','../','a0',1,'００'):
            with self.subTest(value=value),self.assertRaises(ValueError):selected_index(value,2)

    def test_new_options_validate_without_altering_hctp_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            for role in ('ring','entrance'):
                for profile in ('Standard','Preserve Hands','Preserve Arms'):
                    self.request(tmp,costume_role=role,wii_geometry=profile,source_entry='01').validate()
            r=self.request(tmp)
            Request(r.source,r.base).validate()
            with self.assertRaisesRegex(ValueError,'Entrance budget'):Request(r.source,r.base,costume_role='entrance').validate()
            with self.assertRaisesRegex(ValueError,'Wii geometry'):Request(r.source,r.base,wii_geometry='Preserve Arms').validate()

    def test_wii_does_not_silently_ignore_unsupported_texture_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ('ATO','Priority Selection','Legacy','Maximum Downgrade'):
                with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'Default textures only'):self.request(tmp,texture_mode=mode).validate()
            with self.assertRaises(ValueError):self.request(tmp,source_entry='../x').validate()
            with self.assertRaises(ValueError):self.request(tmp,costume_role='unknown').validate()

    def test_dispatch_does_not_call_hctp_prepare(self):
        req=Request('source.pac','base.pac',source_format='wwe13-wii')
        with patch('desktop.wii_job.run_job',return_value={'format':'wii'}) as job,patch('desktop.core.prepare',side_effect=AssertionError('HCTP called')):
            self.assertEqual(run_job(req,'work'),{'format':'wii'})
            self.assertIs(job.call_args.args[0],req)

    def test_cancel_before_decoding_or_launching_blender(self):
        with tempfile.TemporaryDirectory() as tmp:
            request=self.request(tmp)
            with patch('desktop.wii_job.bundles',side_effect=AssertionError('decoder called')):
                with self.assertRaises(Cancelled):run_job(request,Path(tmp)/'work',cancel=lambda:True)

    @unittest.skipUnless(BASE.is_file(),'Development-only donor rig not present')
    def test_procedural_wii_catalogue_and_source_preview_are_readonly(self):
        from tools.wii_fixture import create
        with tempfile.TemporaryDirectory() as tmp:
            path=create(BASE,Path(tmp)/'fixture');before=path.read_bytes();reader=adapter('wwe13-wii')
            catalogue=reader.catalogue(path);self.assertEqual([r['id'] for r in catalogue['entries']],['00','01'])
            info=reader.inspect(path,Path(tmp)/'images',entry_id='01')
            self.assertEqual(info['selected_entry'],'01');self.assertGreater(info['triangles'],0)
            self.assertTrue(all(Path(p['png']).is_file() for p in info['texture_previews']))
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(ValueError):reader.inspect(path,entry_id='02')

    def test_epk8_magic_alone_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'not-wii.pac';p.write_bytes(b'EPK8'+bytes(4092))
            with self.assertRaises(ValueError):adapter('wwe13-wii').catalogue(p)

    def test_entrance_save_as_uses_role_limit_and_preserves_inputs(self):
        raw=(FIXTURES/'psp-quad.pac').read_bytes();raw+=bytes(153600-len(raw))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);a=p/'source.pac';b=p/'base.pac';c=p/'candidate.pac'
            for f in (a,b,c):f.write_bytes(raw)
            result=dict(pac=str(c),source=str(a),base=str(b),sha256=digest(c),source_format='wwe13-wii',costume_role='entrance')
            save_as(result,p/'saved.pac');self.assertEqual((p/'saved.pac').read_bytes(),raw)
            self.assertEqual(a.read_bytes(),raw);self.assertEqual(b.read_bytes(),raw)
            with self.assertRaisesRegex(ValueError,'size/alignment'):save_as(dict(result,costume_role='ring'),p/'ring.pac')
            with self.assertRaises(ValueError):save_as(dict(result,costume_role='invented'),p/'bad.pac')

    def test_format_aware_allocation_patches_only_control_and_checks_actual_size(self):
        base=(FIXTURES/'psp-quad.pac').read_bytes();original=(FIXTURES/'psp-quad.yobj').read_bytes()
        raw,_=patch_regular_depths(original,{'skin':8});model=audit_yobj(raw);model['textures']=model['texture_names']
        gim=(FIXTURES/'skin-t4.gim').read_bytes();ix,pal=read_gim(gim)
        entry=dict(width=ix.shape[1],height=ix.shape[0],bits=4,individual_bpe_bytes=len(gim),pixel_palette_bytes=len(gim)-208,metrics={'perceptual_loss':0.})
        factory=lambda *args:([[dict(raw=gim,entry=dict(entry))]],[1.],[dict(name='skin')])
        with tempfile.TemporaryDirectory() as tmp:
            pac,gims,report=allocate(base,raw,model,[pal[ix]],[dict(bits=8,cutout=False)],Path(tmp)/'good',candidate_factory=factory,format_aware=True)
            native=next(r for s,r in sections(pac) if s['id']==2)
            self.assertEqual(native,original);self.assertTrue(report['format_aware_material_depths'])
            self.assertEqual(report['pac_bytes'],len(pac));self.assertEqual(gims['skin'],gim)
            with self.assertRaisesRegex(ValueError,'minimum does not fit'):
                allocate(base,raw,model,[pal[ix]],[dict(bits=8,cutout=False)],Path(tmp)/'small',candidate_factory=factory,format_aware=True,target=1)

    def test_opaque_candidates_recheck_full_frontier_and_source_ceilings(self):
        from tests.test_wwe13_wii_corpus import model
        from desktop.wii_textures import candidates
        m=model();m['textures']=['skin'];m['bones'][0]['name']='atama'
        y,x=np.indices((32,64));im=np.stack([x*4,y*8,(x+y)*2,np.full_like(x,255)],axis=2).astype(np.uint8)
        choices,importance,diag=candidates(m,[im],[dict(bits=8,cutout=False)],lambda *a,**k:None)
        self.assertTrue(choices[0]);self.assertTrue(diag[0]['rejected'])
        for row in choices[0]:
            ix,pal=read_gim(row['raw']);e=row['entry']
            self.assertLessEqual(ix.shape[1],64);self.assertLessEqual(ix.shape[0],32)
            self.assertIn('native_grid_quantization_rgb_rmse_255',e['metrics'])
            self.assertGreaterEqual(e['requested_useful_colors'],32)

    def test_source_ocular_role_survives_small_transferred_eye_weights(self):
        from tests.test_wwe13_wii_corpus import model
        from desktop.wii_textures import candidates
        m=model();m['textures']=['skin'];m['bones'][0]['name']='atama';m['texture_region_hints']={'skin':'ocular'}
        y,x=np.indices((66,33));im=np.stack([x*7,y*3,(x+y)*2,np.full_like(x,255)],axis=2).astype(np.uint8)
        choices,importance,diag=candidates(m,[im],[dict(bits=8,cutout=False)],lambda *a,**k:None)
        self.assertTrue(diag[0]['ocular_surface'])
        self.assertTrue(all((r['entry']['width'],r['entry']['height'])==(32,64) for r in choices[0]))
        self.assertTrue(all(r['entry']['requested_useful_colors']>=64 for r in choices[0]))

    def test_cutout_candidates_preserve_nearest_alpha_and_half_source_floor(self):
        from tests.test_wwe13_wii_corpus import model
        from desktop.wii_textures import candidates
        m=model();m['textures']=['skin']
        y,x=np.indices((128,64));im=np.full((128,64,4),255,np.uint8);im[:,:,3]=np.where((x+y)%4==0,0,255)
        choices,_,_=candidates(m,[im],[dict(bits=8,cutout=True)],lambda *a,**k:None)
        for row in choices[0]:
            ix,pal=read_gim(row['raw']);self.assertGreaterEqual(ix.shape[1],32);self.assertGreaterEqual(ix.shape[0],64)
            nearest=np.asarray(Image.fromarray(im[:,:,3]).resize((ix.shape[1],ix.shape[0]),Image.Resampling.NEAREST))
            np.testing.assert_array_equal(pal[ix][:,:,3],nearest)


if __name__=='__main__':unittest.main()
