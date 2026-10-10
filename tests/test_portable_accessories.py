"""Generated geometry only: independent rigs, shared dependency closure and bounds."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from desktop.accessories import source_models,build_accessories,package_models,combined_preview,validate_accessory
from desktop.core import validate_pac
from tools.generate_conformance_fixtures import vectors,pac
from tools.hctp_weights import read_hctp_with_weights
from tools.pac_inspect import inspect_pac
from tools.pac_repack import texture_table,replace_sections,rewrite_sections
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections


def named(raw,texture='skin',side='l'):
    raw=bytearray(raw);bones=struct.unpack_from('<I',raw,40)[0]+8
    for i,name in enumerate((side+'_ninoude',side+'_kote')):
        raw[bones+80*i:bones+80*i+16]=name.encode().ljust(16,b'\0')
    tex=struct.unpack_from('<I',raw,44)[0]+8
    raw[tex:tex+16]=texture.encode().ljust(16,b'\0')
    return bytes(raw)


class AccessoriesTests(unittest.TestCase):
    def setUp(self):
        self.files=vectors();self.main=named(self.files['hctp-quad.yobj'])
        self.pad=named(self.files['hctp-quad.yobj'],'pad')
        self.source=read_hctp_with_weights(self.main)
        self.target=audit_yobj(named(self.files['psp-quad.yobj']))
        self.target['bone_count']=len(self.target['bones'])
        self.target['textures']=self.target['texture_names']
        self.alignment=dict(scale=1.,rotation=np.eye(3).tolist(),translation=[0,0,0])

    def read_set(self,entries):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pac';path.write_bytes(pac(entries))
            return source_models(path,self.source)

    def test_role_and_texture_closure_not_file_order_or_model_name(self):
        items,names=self.read_set([(6,self.pad),(2,self.main),(50,b'opaque')])
        self.assertEqual(names,['skin','pad']);self.assertEqual(items[0]['target_section'],26)
        self.assertEqual(items[0]['support'],['l_kote','l_ninoude'])
        self.assertEqual(items[0]['model']['model_name'],'synthetic')

    def test_unknown_wrong_side_and_duplicate_sections_are_not_silently_dropped(self):
        for entries,message in (([(2,self.main),(12,self.pad)],'Unrecognized'),
                                ([(2,self.main),(7,self.pad)],'controller contract'),
                                ([(2,self.main),(6,self.pad),(6,self.pad)],'Duplicate'),
                                ([(2,self.main),(6,b'not a model')],'not a supported')):
            with self.subTest(message=message),self.assertRaisesRegex(ValueError,message):self.read_set(entries)

    def test_accessory_bind_chain_difference_rejected(self):
        pad=bytearray(self.pad);bones=struct.unpack_from('<I',pad,40)[0]+8
        struct.pack_into('<f',pad,bones+16,10.)
        with self.assertRaisesRegex(ValueError,'rest hierarchy'):self.read_set([(2,self.main),(6,bytes(pad))])

    def build(self):
        items,names=self.read_set([(2,self.main),(6,self.pad)])
        return build_accessories(items,self.target,self.alignment,[dict(name='pad',bits=4,cutout=False)])

    def test_all_accessory_attributes_topology_and_poses_survive_native_writing(self):
        models,expected,reports=self.build();native=audit_yobj(models[26])
        self.assertEqual(reports[0]['source_triangles'],2);self.assertEqual(reports[0]['triangles'],2)
        self.assertFalse(reports[0]['decimation_applied'])
        self.assertEqual(native['texture_names'],['pad'])
        self.assertTrue(all(row['maximum_position_delta']==0 for row in reports[0]['analytical_validation']['poses'].values()))
        bad=copy.deepcopy(native);bad['meshes'][0]['vertices'][0]['weights']=[0.,1.]
        with self.assertRaisesRegex(ValueError,'weights'):validate_accessory(expected[26],bad)
        bad=copy.deepcopy(native);bad['meshes'][0]['vertices'][0]['uv']=[.5,.5]
        with self.assertRaisesRegex(ValueError,'uv'):validate_accessory(expected[26],bad)

    def test_all_models_are_checked_and_unrelated_base_payload_is_exact(self):
        models,expected,reports=self.build()
        base=pac([(2,named(self.files['psp-quad.yobj'])),(9,texture_table(['skin'],[self.files['skin-t4.gim']])),(50,b'untouched')])
        table=texture_table(['skin','pad'],[self.files['skin-t4.gim']]*2)
        candidate=package_models(base,named(self.files['psp-quad.yobj']),table,models)
        native,gims=validate_pac(candidate,base,accessory_models=expected)
        self.assertEqual(set(gims),{'skin','pad'})
        self.assertEqual([s['id'] for s in inspect_pac(candidate)['sections']],[2,9,50,26])
        self.assertEqual(next(r for s,r in sections(candidate) if s['id']==50),b'untouched')
        malformed=bytearray(models[26]);mesh=struct.unpack_from('<I',malformed,36)[0]+8
        material=struct.unpack_from('<I',malformed,mesh+12)[0]+8
        index=struct.unpack_from('<I',malformed,material+140)[0]+8
        struct.pack_into('<H',malformed,index,65535)
        bad=package_models(base,named(self.files['psp-quad.yobj']),table,{26:bytes(malformed)})
        with self.assertRaisesRegex(ValueError,'Index outside'):validate_pac(bad,base,accessory_models=expected)
        missing=package_models(base,named(self.files['psp-quad.yobj']),texture_table(['skin'],[self.files['skin-t4.gim']]),models)
        with self.assertRaisesRegex(ValueError,'texture table'):validate_pac(missing)

    def test_preview_remaps_independent_texture_indices_without_mutation(self):
        models,expected,reports=self.build();main=copy.deepcopy(self.target)
        main['texture_names'].append('pad');pad=audit_yobj(models[26])
        combined=combined_preview(main,[pad])
        self.assertEqual(len(combined['meshes']),2)
        self.assertEqual(combined['meshes'][1]['materials'][0]['texture_id'],1)
        self.assertEqual(pad['meshes'][0]['materials'][0]['texture_id'],0)
        self.assertEqual(len(main['meshes']),1)

    def test_replacement_contract_and_explicit_addition_collision(self):
        base=self.files['psp-quad.pac']
        with self.assertRaises(ValueError):replace_sections(base,{26:b'x'})
        with self.assertRaises(ValueError):rewrite_sections(base,{},additions={2:b'x'})
        self.assertEqual(replace_sections(base,{}),rewrite_sections(base,{},additions={}))


if __name__=='__main__':unittest.main()
