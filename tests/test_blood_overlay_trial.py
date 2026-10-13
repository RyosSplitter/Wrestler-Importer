"""Generated overlay fixtures: no original game assets required."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from tools.psp_blood_overlay_trial import fit_layers, validate_layers, run
from tools.pac_repack import replace_sections, texture_table
from tools.texture_convert import write_gim4
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model


def vectors():
    body = audit_yobj(Path('tests/fixtures/hctp_psp/psp-quad.yobj').read_bytes())
    donor = copy.deepcopy(body)
    donor['texture_names'] = ['skin','blood','blood_b']
    donor['texture_raw'] = b''.join(n.encode().ljust(16,b'\0') for n in donor['texture_names'])
    header = bytearray(donor['header']); struct.pack_into('<I',header,32,3)
    donor['header'] = bytes(header)
    for i in (1,2):
        mesh = copy.deepcopy(body['meshes'][0]); mesh['index'] = i
        for v in mesh['vertices']:
            v['position'] = [*v['position'][:2],.02]
        raw = bytearray(mesh['materials'][0]['raw'])
        struct.pack_into('<H',raw,22,i); struct.pack_into('<I',raw,24,0x115)
        mesh['materials'][0].update(raw=bytes(raw),texture_id=i,control=0x115)
        donor['meshes'].append(mesh)
    return body, donor


class BloodOverlayTests(unittest.TestCase):
    def test_existing_skin_records_remain_exact_and_inputs_are_immutable(self):
        body, donor = vectors(); original = copy.deepcopy(body); d = copy.deepcopy(donor)
        model, records, report = fit_layers(body, donor)
        self.assertEqual(body, original); self.assertEqual(donor, d)
        native = audit_yobj(write_model(model,[[i] for i in range(len(model['meshes']))]))
        validation = validate_layers(body, native, records)
        self.assertEqual(validation['body']['status'],'pass')
        self.assertEqual(native['meshes'][0]['raw_vertices'], body['meshes'][0]['raw_vertices'])
        self.assertEqual(report['blood']['added_triangles'],2)
        self.assertAlmostEqual(report['blood']['applied_normal_offset'],.02)
        for r in records:
            a = native['meshes'][r['mesh']]['vertices'][r['vertex']]
            b = body['meshes'][r['body_mesh']]['vertices'][r['body_vertex']]
            self.assertEqual(a['weights'],b['weights'])

    def test_coincident_control_has_zero_geometric_attachment_error(self):
        body, donor = vectors(); model, records, report = fit_layers(body,donor,coincident=True)
        native = audit_yobj(write_model(model,[[i] for i in range(len(model['meshes']))]))
        check = validate_layers(body,native,records)
        self.assertTrue(all(v==0 for v in check['overlay_pose_gaps'].values()))
        self.assertTrue(all(v==0 for v in check['overlay_cranial_gaps'].values()))
        self.assertEqual(report['blood']['applied_normal_offset'],0)

    def test_material_state_is_copied_except_texture_index_and_writer_pointers(self):
        body, donor = vectors(); model, records, _ = fit_layers(body,donor)
        native = audit_yobj(write_model(model,[[i] for i in range(len(model['meshes']))]))
        for m in native['meshes'][1:]:
            a = m['materials'][0]; n = native['texture_names'][a['texture_id']]
            old = next(x['materials'][0] for x in donor['meshes'][1:] if donor['texture_names'][x['materials'][0]['texture_id']]==n)
            self.assertEqual(a['raw'][:22],old['raw'][:22])
            self.assertEqual(a['raw'][24:132],old['raw'][24:132])
            self.assertEqual(a['control'],0x115)

    def test_rig_mismatch_existing_blood_and_missing_patch_are_refused(self):
        body, donor = vectors(); bad = copy.deepcopy(donor); bad['bone_raw'] += b'\0'
        with self.assertRaisesRegex(ValueError,'bind rigs'):fit_layers(body,bad)
        bad = copy.deepcopy(body); bad['texture_names'].append('blood')
        with self.assertRaisesRegex(ValueError,'already contains'):fit_layers(bad,donor)
        bad = copy.deepcopy(donor); bad['meshes'].pop()
        with self.assertRaisesRegex(ValueError,'face and torso'):fit_layers(body,bad)

    def test_valid_but_changed_overlay_weights_are_detected(self):
        body, donor = vectors(); model, records, _ = fit_layers(body,donor)
        native = audit_yobj(write_model(model,[[i] for i in range(len(model['meshes']))]))
        r = next(r for r in records if body['meshes'][r['body_mesh']]['vertices'][r['body_vertex']]['weights']==[.25,.75])
        native['meshes'][r['mesh']]['vertices'][r['vertex']]['weights'] = [.3,.7]
        with self.assertRaisesRegex(ValueError,'different facial/body skinning'):validate_layers(body,native,records)

    def test_off_surface_layer_is_detected_even_with_valid_weights(self):
        body, donor = vectors(); model, records, _ = fit_layers(body,donor)
        native = audit_yobj(write_model(model,[[i] for i in range(len(model['meshes']))]))
        r = records[0]; v = native['meshes'][r['mesh']]['vertices'][r['vertex']]
        v['position'] = (np.array(v['position'])+[0,0,.5]).tolist()
        with self.assertRaisesRegex(ValueError,'separates'):validate_layers(body,native,records)

    def test_oversize_trial_preserves_inputs_and_withholds_pac(self):
        body, donor = vectors()
        for m in donor['meshes']:
            m['raw_vertices'] = b''.join(struct.pack('<'+'f'*m['weight_slots']+'2f4B6f',
                *v['weights'],*v['uv'],*v['color'],*v['normal'],*v['position']) for v in m['vertices'])
        raw = write_model(donor,[[i] for i in range(len(donor['meshes']))])
        palette = np.zeros((16,4),dtype=np.uint8);palette[1]=[160,0,0,255]
        pixels = np.ones((8,32),dtype=np.uint8);pixels[0,0]=0
        gim = write_gim4(pixels,palette)
        baseline = Path('tests/fixtures/hctp_psp/psp-quad.pac').read_bytes()
        donor_pac = replace_sections(baseline,{2:raw,9:texture_table(donor['texture_names'],[gim]*3)})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d);(p/'body.pac').write_bytes(baseline);(p/'donor.pac').write_bytes(donor_pac)
            result = run(p/'body.pac',p/'donor.pac',p/'output',max_bytes=1)
            self.assertIn('withheld',result['status'])
            self.assertFalse(list((p/'output').glob('*.pac')))
            self.assertEqual((p/'body.pac').read_bytes(),baseline)
            self.assertEqual((p/'donor.pac').read_bytes(),donor_pac)

    def test_added_index_corruption_is_refused_by_native_auditor(self):
        body, donor = vectors(); model, _, _ = fit_layers(body,donor)
        raw = bytearray(write_model(model,[[i] for i in range(len(model['meshes']))]))
        native = audit_yobj(raw);m = native['report']['mesh_reports'][1]
        index = m['submeshes'][0]['index_ranges'][0]['start']
        struct.pack_into('<H',raw,index,m['vertices'])
        with self.assertRaisesRegex(ValueError,'Index outside'):audit_yobj(raw)


if __name__=='__main__':unittest.main()
