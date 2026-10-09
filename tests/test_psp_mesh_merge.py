"""Integration and corruption checks against the published, working Lance fixture."""
from pathlib import Path
import struct
import unittest

from tools.pac_inspect import inspect_pac
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import compatible, plan, rebuild, verify
from tools.yukes_bpe import decompress


class MeshMergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pac = (Path(__file__).resolve().parents[1]/'downloads/1800-PSP-hybrid-half-textures.pac').read_bytes()
        section = next(s for s in inspect_pac(pac)['sections'] if s['id']==2)
        cls.data = decompress(pac[section['offset']:section['offset']+section['size']])
        cls.model = audit_yobj(cls.data)

    def test_lossless_slot_remap_and_strip_offsets(self):
        # Actual adjacent, differently sized palettes require adding/remapping
        # slots, not just concatenating buffers with their old stride.
        groups = [[i] for i in range(57) if i!=26]
        groups[25].append(26)
        parts = [i for i in range(57)];parts[26]=parts[25]
        after = rebuild(self.data,groups,parts)
        self.assertTrue(verify(self.data,after,groups)['per_bone_nonzero_weight_bits_identical'])
        merged = audit_yobj(after)['meshes'][25]
        self.assertEqual(merged['bone_palette'],list(dict.fromkeys(self.model['meshes'][25]['bone_palette']+self.model['meshes'][26]['bone_palette'])))
        self.assertEqual(len(merged['vertices']),sum(len(self.model['meshes'][i]['vertices']) for i in (25,26)))

    def test_reject_palette_overflow_and_cross_part_and_nonadjacent(self):
        self.assertTrue(compatible(self.model['meshes'][:2],[0,0]))
        self.assertTrue(compatible(self.model['meshes'][25:27],[0,1]))
        self.assertTrue(compatible([self.model['meshes'][25],self.model['meshes'][27]],[0,0]))

    def test_overlapping_choices_prefer_less_expanded_vertex_data(self):
        parts=list(range(57))
        for start in (25,34):parts[start:start+3]=[start]*3
        groups=plan(self.model,parts)
        self.assertIn([26,27],groups)
        self.assertIn([35,36],groups)
        self.assertNotIn([25,26],groups)
        self.assertNotIn([34,35],groups)

    def test_reject_invalid_vertex_index(self):
        bad = bytearray(self.data)
        r = self.model['report']['mesh_reports'][0]
        ip = r['submeshes'][0]['index_ranges'][0]['start']
        struct.pack_into('<H',bad,ip,r['vertices'])
        with self.assertRaisesRegex(ValueError,'Index outside'):audit_yobj(bad)

    def test_reject_secondary_mesh_count_mismatch(self):
        bad = bytearray(self.data)
        name = struct.unpack_from('<I',bad,48)[0]+8
        struct.pack_into('<I',bad,name+24,56)
        with self.assertRaisesRegex(ValueError,'Secondary descriptor'):audit_yobj(bad)

    def test_opaque_mesh_state_prevents_merge(self):
        bad=bytearray(self.data)
        start=struct.unpack_from('<I',bad,36)[0]+8
        struct.pack_into('<I',bad,start+26*64+32,1)
        changed=audit_yobj(bad)
        self.assertIn('Different opaque mesh metadata',compatible(changed['meshes'][25:27],[8,8]))

    def test_preservation_verifier_rejects_render_state_change(self):
        groups=[[i] for i in range(57)]
        after=bytearray(rebuild(self.data,groups,list(range(57))))
        start=struct.unpack_from('<I',after,36)[0]+8
        material=struct.unpack_from('<I',after,start+12)[0]+8
        after[material]^=1
        audit_yobj(after)
        with self.assertRaisesRegex(ValueError,'render state'):verify(self.data,after,groups)

    def test_reject_bone_and_weight_corruption(self):
        bad = bytearray(self.data)
        start = struct.unpack_from('<I',bad,36)[0]+8
        palette = struct.unpack_from('<I',bad,start+8)[0]+8
        struct.pack_into('<I',bad,palette+16,80)
        with self.assertRaisesRegex(ValueError,'bone palette'):audit_yobj(bad)
        bad = bytearray(self.data)
        vp = self.model['report']['mesh_reports'][0]['vertex_buffer_start']
        struct.pack_into('<f',bad,vp,2)
        with self.assertRaisesRegex(ValueError,'vertex attributes'):audit_yobj(bad)

    def test_reject_alias_pointer_and_relocation_corruption(self):
        bad = bytearray(self.data)
        start = struct.unpack_from('<I',bad,36)[0]+8
        material = struct.unpack_from('<I',bad,start+12)[0]+8
        struct.pack_into('<I',bad,material+140,struct.unpack_from('<I',bad,material+140)[0]+4)
        with self.assertRaisesRegex(ValueError,'alias disagrees'):audit_yobj(bad)
        bad = bytearray(self.data)
        pof = struct.unpack_from('<I',bad,4)[0]+8
        bad[pof+8]=0
        with self.assertRaisesRegex(ValueError,'relocation data'):audit_yobj(bad)

    def test_semantic_verifier_detects_valid_weight_change(self):
        groups = [[i] for i in range(57)]
        after = bytearray(rebuild(self.data,groups,list(range(57))))
        mesh = audit_yobj(after)['meshes'][25]
        report = audit_yobj(after)['report']['mesh_reports'][25]
        for vi,v in enumerate(mesh['vertices']):
            slots = [i for i,w in enumerate(v['weights']) if w>.01]
            if len(slots)>=2:
                a,b=slots[:2];vp=report['vertex_buffer_start']+vi*mesh['stride']
                struct.pack_into('<f',after,vp+4*a,v['weights'][a]-.005)
                struct.pack_into('<f',after,vp+4*b,v['weights'][b]+.005)
                break
        else:self.fail('Fixture lacks blended weights')
        audit_yobj(after)  # Normalized weights alone are insufficient.
        with self.assertRaisesRegex(ValueError,'per-bone weight'):verify(self.data,after,groups)


if __name__=='__main__':unittest.main()
