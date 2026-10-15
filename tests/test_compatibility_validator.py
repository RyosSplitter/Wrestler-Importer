"""Real scoped compatibility repairs against a generated PSP base (no game art)."""
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from desktop.pac_validator import validate_pac
from desktop import compatibility_validation as cv
from desktop.texture_optimizer.candidates import read_gim,write_gim
from tools.generate_conformance_fixtures import vectors,pac
from tools.pac_repack import texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections
from tests.test_portable_skinning import one_slot_model


def payloads(data):return {s['id']:raw for s,raw in sections(data)}


def linear_gim(raw):
    b=bytearray(raw);fmt,order,w,h,bits=struct.unpack_from('<5H',raw,68)
    pitch=((w*bits+7)//8+15)//16*16;ph=(h+7)//8*8
    y,x=np.indices((ph,pitch));a=((y//8)*(pitch//16)+x//16)*128+(y%8)*16+x%16
    end=128+pitch*ph
    b[128:end]=np.frombuffer(raw[128:end],np.uint8)[a].tobytes();struct.pack_into('<H',b,70,0)
    return bytes(b)


def table_unchecked(name,raw):
    return struct.pack('<4I',1,0x100,0,16)+name.encode().ljust(16,b'\0')+b'gim\0'+struct.pack('<3I',len(raw),48,0)+raw


class CompatibilityValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.f=vectors()

    def run_case(self,root,data,mode='full',**kwargs):
        source=root/'Source.pac';source.write_bytes(data)
        base=root/'Base.pac';base.write_bytes(self.f['psp-quad.pac'])
        r=validate_pac(source,root/'qa',base=base,mode=mode,resolution=96,**kwargs)
        self.assertEqual(source.read_bytes(),data)
        self.assertEqual(base.read_bytes(),self.f['psp-quad.pac'])
        self.assertTrue(r['input_unchanged']);self.assertTrue(r['base_unchanged'])
        self.assertTrue(Path(r['report_path']).is_file())
        return r

    def source(self,model=None,image=None):
        f=self.f;tex=table_unchecked('skin',image) if image else payloads(f['psp-quad.pac'])[9]
        return pac([(2,model or f['psp-quad.yobj']),(9,tex),(50,b'opaque unrelated payload')])

    def test_healthy_full_is_viewable_without_matching_donor_counts(self):
        data=self.source()
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data)
            self.assertTrue(r['selected_validation_passed'],r['repair_failures'])
            self.assertTrue(r['app_viewable']);self.assertIsNone(r['repaired_pac'])
            self.assertEqual(r['repairs'],[])

    def test_texture_only_linear_repair_preserves_models_and_rgba_exactly(self):
        original=self.f['skin-t4.gim'];p,c=read_gim(original)
        with tempfile.TemporaryDirectory() as t:
            data=self.source(image=linear_gim(original));r=self.run_case(Path(t),data,'textures')
            self.assertTrue(r['selected_validation_passed'],r)
            self.assertTrue(r['app_viewable'])
            final=payloads(Path(r['repaired_pac']).read_bytes())
            before=payloads(data)
            self.assertEqual(final[2],before[2]);self.assertEqual(final[50],before[50])
            # Recovered image comparison uses the actual checked table inventory.
            inv=cv.inventory(Path(r['repaired_pac']).read_bytes());row=inv['textures'][0]
            np.testing.assert_array_equal(row['colors'][row['pixels']],c[p])
            self.assertFalse(r['after']['checked']['model'])

    def test_model_only_preserves_stored_texture_payload_and_uses_base_slots(self):
        data=self.source(model=one_slot_model())
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data,'model');self.assertTrue(r['selected_validation_passed'],r)
            a,b=payloads(data),payloads(Path(r['repaired_pac']).read_bytes())
            self.assertEqual(a[9],b[9]);self.assertEqual(a[50],b[50])
            before,after=audit_yobj(a[2]),audit_yobj(b[2])
            self.assertEqual(before['bone_raw'],after['bone_raw'])
            self.assertEqual(len(after['meshes'][0]['bone_palette']),2)
            self.assertEqual(before['report']['vertices'],after['report']['vertices'])

    def test_broken_size_alias_and_linear_texture_need_full_to_repair_both(self):
        model=bytearray(self.f['psp-quad.yobj']);struct.pack_into('<I',model,12,0)
        image=linear_gim(self.f['skin-t4.gim']);data=self.source(bytes(model),image)
        for mode in ('textures','model','full'):
            with tempfile.TemporaryDirectory() as t:
                r=self.run_case(Path(t),data,mode)
                self.assertTrue(r['selected_validation_passed'],r)
                self.assertIsNotNone(r['repaired_pac'])
                final=payloads(Path(r['repaired_pac']).read_bytes())
                if mode=='textures':self.assertEqual(final[2],bytes(model));self.assertFalse(r['app_viewable'])
                if mode=='model':self.assertEqual(final[9],payloads(data)[9]);self.assertFalse(r['app_viewable'])
                if mode=='full':self.assertTrue(r['app_viewable'])

    def test_texture_only_corrects_depth_without_changing_material_records(self):
        p=np.zeros((32,32),np.uint8);p[:,16:]=1;c=np.zeros((256,4),np.uint8)
        c[0]=[255,20,30,255];c[1]=[1,22,33,0]
        data=self.source(image=write_gim(p,c,8))
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data,'textures');self.assertTrue(r['selected_validation_passed'],r)
            final=payloads(Path(r['repaired_pac']).read_bytes())
            self.assertEqual(final[2],payloads(data)[2])
            row=cv.inventory(Path(r['repaired_pac']).read_bytes())['textures'][0]
            self.assertEqual(len(row['colors']),16)
            np.testing.assert_array_equal(row['colors'][row['pixels']],c[p])

    def test_full_prefers_preserving_pixels_and_repairs_model_material_depth(self):
        p=np.zeros((32,32),np.uint8);c=np.zeros((256,4),np.uint8);c[0]=[170,180,190,255]
        data=self.source(image=write_gim(p,c,8))
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data);self.assertTrue(r['selected_validation_passed'],r)
            final=payloads(Path(r['repaired_pac']).read_bytes())
            self.assertEqual(final[9],payloads(data)[9])
            self.assertEqual(audit_yobj(final[2])['meshes'][0]['materials'][0]['control'],7)

    def test_redundant_gim_lengths_are_recovered_not_truncated(self):
        original=self.f['skin-t4.gim'];broken=bytearray(original);struct.pack_into('<I',broken,20,0)
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),self.source(image=bytes(broken)))
            self.assertTrue(r['selected_validation_passed'],r)
            row=cv.inventory(Path(r['repaired_pac']).read_bytes())['textures'][0]
            p,c=read_gim(original);np.testing.assert_array_equal(row['colors'][row['pixels']],c[p])

    def test_bad_indices_are_not_deleted_or_copied_from_base(self):
        raw=bytearray(self.f['psp-quad.yobj']);m=audit_yobj(raw)
        start=m['report']['mesh_reports'][0]['submeshes'][0]['index_ranges'][0]['start']
        struct.pack_into('<H',raw,start,65535)
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),self.source(model=bytes(raw)))
            self.assertFalse(r['selected_validation_passed']);self.assertIsNone(r['repaired_pac'])
            self.assertTrue(r['after']['issues']['model'])

    def test_missing_textures_are_not_replaced_with_donor_art(self):
        data=pac([(2,self.f['psp-quad.yobj'])])
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data)
            self.assertFalse(r['selected_validation_passed']);self.assertFalse(r['app_viewable'])
            self.assertIsNone(r['repaired_pac'])

    def test_corrupt_alpha_palette_is_not_reconstructed_from_base(self):
        data=self.source(image=self.f['skin-t4.gim'][:-4])
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data)
            self.assertFalse(r['selected_validation_passed']);self.assertIsNone(r['repaired_pac'])

    def test_check_only_and_budget_enforcement(self):
        for options in (dict(repair=False),dict(max_bytes=32)):
            with tempfile.TemporaryDirectory() as t:
                r=self.run_case(Path(t),self.source(model=one_slot_model()),**options)
                self.assertFalse(r['selected_validation_passed']);self.assertIsNone(r['repaired_pac'])

    def test_existing_output_and_invalid_mode_fail_before_any_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.run_case(root,self.source())
            before=(root/'qa/report.json').read_bytes()
            with self.assertRaises(FileExistsError):validate_pac(root/'Source.pac',root/'qa',base=root/'Base.pac')
            self.assertEqual((root/'qa/report.json').read_bytes(),before)
            with self.assertRaises(ValueError):validate_pac(root/'Source.pac',root/'other',base=root/'Base.pac',mode='bogus')
            self.assertFalse((root/'other').exists())

    def test_no_hctp_base_or_automatic_skeleton_substitution(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'Source.pac';source.write_bytes(self.source())
            base=root/'Base.pac';base.write_bytes(b'not a PSP PAC')
            r=validate_pac(source,root/'qa',base=base,resolution=96)
            self.assertFalse(r['selected_validation_passed']);self.assertIsNone(r['repaired_pac'])
            self.assertEqual(source.read_bytes(),self.source())

    def test_base_mesh_count_and_shape_are_not_targets(self):
        m=audit_yobj(self.f['psp-quad.yobj'])
        import copy
        other=copy.deepcopy(m['meshes'][0]);other['index']=1
        m['meshes'].append(other)
        data=self.source(model=write_model(m,[[0],[1]]))
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data)
            self.assertTrue(r['selected_validation_passed'],r)
            self.assertEqual(r['after']['models'][0]['meshes'],2)
            self.assertIsNone(r['repaired_pac'])

    def test_recoverable_pixel_pointer_aliases_preserve_pixels_and_opaque_bytes(self):
        original=self.f['skin-t4.gim'];bad=bytearray(original)
        bad[14]=77;struct.pack_into('<I',bad,92,0);struct.pack_into('<I',bad,96,0)
        fixed,p,c,proof=cv.recover_gim(bytes(bad))
        a,b=read_gim(original)
        self.assertEqual(fixed[14],77)
        np.testing.assert_array_equal(p,a);np.testing.assert_array_equal(c,b)
        self.assertTrue(proof['rgba_exact'])

    def test_either_size_or_count_alias_can_be_recovered_from_a_unique_full_audit(self):
        original=self.f['psp-quad.yobj']
        for offset in (4,12,24,struct.unpack_from('<I',original,48)[0]+8+24):
            raw=bytearray(original);struct.pack_into('<I',raw,offset,0)
            fixed,native,patches=cv.repair_model_metadata(bytes(raw))
            self.assertEqual(fixed,original)
            self.assertEqual(native['report']['meshes'],1)
            self.assertTrue(any(p['offset']==offset for p in patches))

    def test_fully_hidden_main_is_not_reported_as_viewable_or_made_opaque(self):
        p,c=read_gim(self.f['skin-t4.gim']);c[:,3]=0
        data=self.source(image=write_gim(p,c,4))
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data)
            self.assertFalse(r['selected_validation_passed']);self.assertFalse(r['app_viewable'])
            self.assertIsNone(r['repaired_pac']);self.assertFalse(r['repairs'])

    def test_texture_mode_cannot_exceed_base_or_input_pixel_allocation(self):
        # Existing T4 pixels paired with a T8 material would require a much
        # larger palette/plane. Model validation can instead fix that material.
        p=np.zeros((128,128),np.uint8);c=np.zeros((16,4),np.uint8);c[0]=[250,40,20,255]
        raw=bytearray(self.f['psp-quad.yobj']);m=audit_yobj(raw)
        materials=struct.unpack_from('<I',raw,struct.unpack_from('<I',raw,36)[0]+8+12)[0]+8
        struct.pack_into('<I',raw,materials+24,7)
        data=self.source(model=bytes(raw),image=write_gim(p,c,4))
        with tempfile.TemporaryDirectory() as t:
            r=self.run_case(Path(t),data,'textures')
            self.assertFalse(r['selected_validation_passed']);self.assertIsNone(r['repaired_pac'])
            self.assertTrue(any('allocation' in v for v in r['after']['issues']['textures']))

if __name__=='__main__':unittest.main()
