"""Procedural Wii geometry fixtures, no copyrighted source assets."""
import copy,struct,unittest
from unittest.mock import patch
import numpy as np
from tools.wwe13_wii_model import blend_weights,read_model,source_bundle


def fixture():
    raw=bytearray(1024)
    struct.pack_into('>H',raw,0x48,4);raw[0x4c:0x52]=bytes([2,7,1,1,10,0])
    for off,ptr in [(0x54,0x100),(0x5c,0x140),(0x60,0x160),(0x68,0x280),(0x6c,0x290),(28,0x200)]:struct.pack_into('>I',raw,off,ptr-8)
    struct.pack_into('>2H',raw,0x70,1,3)
    raw[0x74]=7
    for i,p in [(0,(0,0,0)),(2,(0,0,128)),(3,(128,0,0))]:struct.pack_into('>6h',raw,0x100+i*12,*p,0,0,-4096)
    struct.pack_into('>4H2I',raw,0x140,0,1,2,3,3,0x2c0-8)
    struct.pack_into('>BBHI',raw,0x160,0,1,1,0x168-8)
    struct.pack_into('>I9H',raw,0x168,3,0,0,0,2,0,1,3,0,2)
    struct.pack_into('>I',raw,0x210,0x220-8);struct.pack_into('>H',raw,0x220+70,0)
    raw[0x280:0x284]=bytes([255]*4)
    struct.pack_into('>6h',raw,0x290,0,0,0,1024,1024,0)
    struct.pack_into('>6H',raw,0x2c0,0,0,4096,0,0,4096)
    header=dict(declared_yobj_bytes=len(raw),material_count=1,texture_slot_count=1,texture_slots=['color'],bone_count=3)
    return raw,header


class BlendTests(unittest.TestCase):
    def test_three_bone_is_successive_not_flat(self):
        np.testing.assert_array_equal(blend_weights(3,3072,3072),[.0625,.1875,.75])
    def test_two_bone_order(self):self.assertEqual(blend_weights(2,1024),[.75,.25])
    def test_three_bone_zero_last_equals_two(self):
        for a in range(0,4097,256):self.assertEqual(blend_weights(3,a,0)[:2],blend_weights(2,a))
    def test_permuted_equivalent_boundary(self):
        a=np.array(blend_weights(2,1024));b=np.array(blend_weights(3,3072,0))
        np.testing.assert_array_equal(a,b[[1,0]])
    def test_sum_and_range(self):
        for a in range(0,4097,256):
            for b in range(0,4097,256):
                w=blend_weights(3,a,b);self.assertEqual(sum(w),1.);self.assertTrue(min(w)>=0)
    def test_invalid_rejected(self):
        for args in [(0,0,0),(4,0,0),(2,0,1),(3,4097,0),(3,-1,0)]:
            with self.assertRaises(ValueError):blend_weights(*args)


class ReaderTests(unittest.TestCase):
    def read(self,raw,header):
        with patch('tools.wwe13_wii_model.read_model_header',return_value=header):return read_model(bytes(24)+bytes(raw))
    def test_padding_does_not_shift_skinning(self):
        raw,h=fixture();m=self.read(raw,h);vs=m['meshes'][0]['vertices']
        self.assertEqual([v['source_position_index']for v in vs],[0,2,3])
        self.assertEqual([v['weights']for v in vs],[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        self.assertEqual(m['source_decode_report']['zero_unreferenced_padding'],[1])
    def test_normal_axes_and_triangle_winding(self):
        raw,h=fixture();m=self.read(raw,h)
        self.assertEqual(m['source_decode_report']['winding'][0]['normal_winding_agreement'],1.)
        self.assertEqual(m['meshes'][0]['vertices'][0]['normal'],[0.,1.,0.])
    def test_corner_bounds(self):
        for offset in (0x16c,0x16e,0x170):
            raw,h=fixture();struct.pack_into('>H',raw,offset,99)
            with self.assertRaises(ValueError):self.read(raw,h)
    def colorless(self):
        raw,h=fixture();raw[0x4d]=3
        struct.pack_into('>I',raw,0x68,0)
        struct.pack_into('>H',raw,0x70,0)
        struct.pack_into('>6H',raw,0x16c,0,0,2,1,3,2)
        return raw,h
    def test_position_uv_pairs_preserve_all_source_attributes_without_phantom_color(self):
        original,h=fixture();expected=self.read(original,h)
        raw,h=self.colorless();before=bytes(raw);actual=self.read(raw,h)
        self.assertEqual(bytes(raw),before)
        self.assertEqual(actual['meshes'],expected['meshes'])
        self.assertFalse(actual['source_decode_report']['source_vertex_colors_present'])
        self.assertEqual(actual['source_decode_report']['source_corner_index_width'],2)
        self.assertEqual(actual['source_decode_report']['referenced_positions'],3)
    def test_colorless_position_and_uv_bounds_are_checked(self):
        for offset in (0x16c,0x16e):
            raw,h=self.colorless();struct.pack_into('>H',raw,offset,99)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'corner outside'):self.read(raw,h)
    def test_colorless_attribute_rejects_nonzero_count_or_pointer(self):
        for field in ('count','pointer'):
            raw,h=self.colorless()
            if field=='count':struct.pack_into('>H',raw,0x70,1)
            else:struct.pack_into('>I',raw,0x68,0x280-8)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'vertex-color'):self.read(raw,h)
    def test_color_attribute_requires_nonempty_color_buffer(self):
        raw,h=fixture();struct.pack_into('>H',raw,0x70,0)
        with self.assertRaisesRegex(ValueError,'vertex-color'):self.read(raw,h)
    def test_invalid_palette(self):
        raw,h=fixture();struct.pack_into('>H',raw,0x140,3)
        with self.assertRaises(ValueError):self.read(raw,h)
    def test_skin_count_mismatch(self):
        raw,h=fixture();struct.pack_into('>I',raw,0x148,2)
        with self.assertRaises(ValueError):self.read(raw,h)
    def test_overlapping_draw_pointer(self):
        raw,h=fixture();struct.pack_into('>I',raw,0x164,0x160-8)
        with self.assertRaises(ValueError):self.read(raw,h)
    def test_material_slot_bounds(self):
        raw,h=fixture();struct.pack_into('>H',raw,0x220+70,1)
        with self.assertRaises(ValueError):self.read(raw,h)
    def test_sample_guard(self):
        with self.assertRaises(ValueError):source_bundle(bytes(1024))
    def test_q8_positions_are_half_q7_without_changing_other_attributes(self):
        raw,h=fixture();before=bytes(raw);a=self.read(raw,h)
        raw[0x74]=8;b=self.read(raw,h)
        for x,y in zip(a['meshes'][0]['vertices'],b['meshes'][0]['vertices']):
            np.testing.assert_array_equal(np.array(x['position'])/2,y['position'])
            for field in ('normal','uv','color','weights','source_position_index','source_skin_group','raw_blend_coefficients'):self.assertEqual(x[field],y[field])
        self.assertEqual(a['meshes'][0]['materials'],b['meshes'][0]['materials'])
        self.assertEqual(a['source_decode_report']['positions_divisor'],128)
        self.assertEqual(b['source_decode_report']['positions_divisor'],256)
        self.assertEqual(raw[:0x74],before[:0x74]);self.assertEqual(raw[0x75:],before[0x75:])
    def test_unknown_position_scale_is_not_silently_assumed_q7(self):
        for fraction in (0,6,9,255):
            raw,h=fixture();raw[0x74]=fraction
            with self.subTest(fraction=fraction),self.assertRaisesRegex(ValueError,'fractional-bit'):self.read(raw,h)
    def test_transparent_material_is_not_assumed_to_be_anatomical_hair(self):
        raw,h=fixture();h['texture_slots']=['trans'];m=self.read(raw,h)
        self.assertEqual(m['meshes'][0]['role'],'Cutout')



class TrialTests(unittest.TestCase):
    def test_eye_pivots_use_source_binds_without_body_or_axis_edits(self):
        from tools.wwe13_wii_trial import fit_ocular
        from tools.prepare_model import bone_matrices
        names=['root','l_eye','r_eye','l_mabuta','r_mabuta'];bones=[];raw=bytearray(80*len(names))
        for i,name in enumerate(names):
            position=[float(i),0.,0.]
            bones.append(dict(index=i,name=name,parent=0 if i else -1,rotation=[0.,0.,.1],local_position=position))
            struct.pack_into('<3f',raw,80*i+16,*position)
        target=dict(bones=bones,bone_raw=bytes(raw));source=copy.deepcopy(target)
        for b in source['bones']:b['local_position']=[v+3. for v in b['local_position']]
        before=copy.deepcopy(target);out,report=fit_ocular(source,target,dict(scale=.1,translation=[0.,0.,0.]))
        self.assertEqual(target,before);self.assertEqual(out['bones'][0],target['bones'][0])
        src,dst=bone_matrices(source),bone_matrices(out)
        np.testing.assert_allclose(src[1:,:3,3]*.1,dst[1:,:3,3],atol=2e-7)
        allowed=set()
        for i in range(1,5):allowed.update(range(i*80+16,i*80+28))
        self.assertTrue(all(i in allowed for i,(a,b)in enumerate(zip(target['bone_raw'],out['bone_raw']))if a!=b))
    def test_alpha_candidates_obey_original_useful_color_ceiling(self):
        from tools.wwe13_wii_trial import candidates
        from desktop.texture_optimizer.candidates import read_gim
        source=np.zeros((32,32,4),np.uint8);source[:16,:,:]=[160,100,60,73];source[16:24,:,:]=[100,50,10,255]
        vertices=[dict(position=p,uv=uv,weights=[1.])for p,uv in zip([[0,0,0],[1,0,0],[0,1,0]],[[0,0],[1,0],[0,1]])]
        model=dict(bones=[dict(index=0,name='root',parent=-1)],textures=['hair'],meshes=[dict(bone_palette=[0],vertices=vertices,materials=[dict(texture_id=0,triangles=[[0,1,2]])])])
        before=source.copy();rows,_,_=candidates(model,[source],[dict(bits=8,cutout=True)],progress=lambda *a,**k:None)
        for r in rows[0]:
            ix,pal=read_gim(r['raw']);decoded=pal[ix]
            self.assertLessEqual(len(np.unique(decoded.reshape(-1,4),axis=0)),3)
            np.testing.assert_array_equal(decoded[:,:,3],source[:,:,3])
            self.assertEqual((r['entry']['width'],r['entry']['height']),(32,32))
        np.testing.assert_array_equal(source,before)

    def test_metadata_validator_rejects_unreported_rotation_change(self):
        from tools.wwe13_wii_trial import check_bone_metadata
        original=dict(bone_raw=bytes(80),bones=[dict(name='root',index=0)])
        altered=bytearray(original['bone_raw']);struct.pack_into('<f',altered,28,.5)
        with self.assertRaises(ValueError):check_bone_metadata(original,dict(bone_raw=bytes(altered)),[])
    def test_metadata_validator_rejects_shrinking_sphere(self):
        from tools.wwe13_wii_trial import check_bone_metadata
        raw=bytearray(80);struct.pack_into('<f',raw,76,2.)
        original=dict(bone_raw=bytes(raw),bones=[dict(name='root',index=0)])
        with self.assertRaises(ValueError):check_bone_metadata(original,original,[dict(bone='root',before=2.,after=1.,maximum_influence_distance=0.)])

    def test_tiny_eye_chart_changes_only_texture_binding(self):
        from tools.wwe13_wii_trial import separate_eye_atlas
        vertices=[dict(position=p,uv=uv,normal=[0.,0.,1.],color=[255]*4,weights=[1.])for p,uv in zip([[0,0,0],[1,0,0],[0,1,0]],[[0,0],[1,0],[0,1]])]
        model=dict(bones=[dict(index=0,name='l_eye')],textures=['color','trans'],texture_count=2,
            meshes=[dict(vertices=vertices,materials=[dict(texture_id=0,triangles=[[0,1,2]])])])
        before=copy.deepcopy(model);im=np.full((32,32,4),100,np.uint8)
        out,images=separate_eye_atlas(model,[im,im])
        self.assertEqual(model,before);self.assertEqual(out['meshes'][0]['vertices'],vertices)
        self.assertEqual(out['meshes'][0]['materials'],[dict(texture_id=2,triangles=[[0,1,2]])])
        np.testing.assert_array_equal(images[2],im);self.assertEqual(out['ocular_atlas_policy']['selected_triangles'],1)

    def test_display_crop_clips_crossing_triangle_instead_of_erasing_it(self):
        from tools.wwe13_wii_export import crop
        vertices=[dict(position=p,uv=[0.,0.],normal=[0.,0.,1.],color=[255]*4,weights=[1.])for p in [[0.,-8.,0.],[1.,-8.,0.],[0.,-6.,0.]]]
        model=dict(meshes=[dict(vertices=vertices,materials=[dict(triangles=[[0,1,2]])])]);before=copy.deepcopy(model)
        shown=crop(model,'head');self.assertEqual(model,before)
        self.assertEqual(len(shown['meshes'][0]['materials'][0]['triangles']),2)
        self.assertTrue(all(v['position'][1]<=-7.05+1e-6 for v in shown['meshes'][0]['vertices']))

if __name__=='__main__':unittest.main()
