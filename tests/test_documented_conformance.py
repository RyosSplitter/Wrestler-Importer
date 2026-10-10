"""Known-answer vectors for a new implementation, independent of game assets.

Expected quad geometry/weights are literal answers, not a reader→writer→reader
roundtrip. Project production writer/compressor is not the fixture generator.
"""
import hashlib
import json
from pathlib import Path
import struct
import unittest

from tools.hctp_weights import decode_weight_packets, read_hctp_with_weights
from tools.pac_inspect import FormatError, inspect_pac
from tools.pac_repack import replace_sections
from tools.psp_mesh_audit import audit_yobj, encode_relocations, relocations
from tools.yukes_bpe import decompress

ROOT = Path(__file__).parent / 'fixtures/hctp_psp'


class DocumentedConformanceTests(unittest.TestCase):
    def raw(self, name):
        return (ROOT/name).read_bytes()

    def test_manifest_and_independent_regeneration(self):
        from tools.generate_conformance_fixtures import vectors
        expected = json.loads(self.raw('expected.json'))
        for name, detail in expected['files'].items():
            raw = self.raw(name)
            self.assertEqual(len(raw), detail['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), detail['sha256'])
        for name, raw in vectors().items():
            self.assertEqual(self.raw(name), raw)

    def test_hctp_corner_geometry_and_explicit_weights(self):
        model = read_hctp_with_weights(self.raw('hctp-quad.yobj'))
        self.assertEqual((model['source_vertex_count'],model['vertex_count'],model['triangle_count']),(4,4,2))
        mesh = model['meshes'][0]
        self.assertEqual(mesh['bone_palette'], [0,1])
        self.assertEqual([list(v['position']) for v in mesh['vertices']],
                         [[0,0,0],[1,0,0],[0,1,0],[1,1,0]])
        self.assertEqual([v['weights'] for v in mesh['vertices']],
                         [[1,0],[.25,.75],[.5,.5],[0,1]])
        self.assertEqual(mesh['materials'][0]['triangles'],[(0,1,2),(1,3,2)])

    def source_corner(self, raw):
        mesh = struct.unpack_from('<I',raw,36)[0]+8
        mat = struct.unpack_from('<I',raw,mesh+12)[0]+8
        strip = struct.unpack_from('<I',raw,mat+200)[0]+8
        return struct.unpack_from('<I',raw,strip+12)[0]+8

    def test_uv_split_copies_verified_source_weights(self):
        raw = bytearray(self.raw('hctp-quad.yobj'))
        corner = self.source_corner(raw)
        struct.pack_into('<I',raw,corner+3*32+12,0)
        model = read_hctp_with_weights(raw)
        vertices = model['meshes'][0]['vertices']
        self.assertEqual(len(vertices),5)
        self.assertEqual(vertices[4]['source_vertex_index'],0)
        self.assertEqual(vertices[4]['position'],vertices[0]['position'])
        self.assertEqual(vertices[4]['weights'],vertices[0]['weights'])
        self.assertNotEqual(vertices[4]['uv'],vertices[0]['uv'])

    def test_strip_degenerate_uses_source_position(self):
        raw = bytearray(self.raw('hctp-quad.yobj'))
        corner = self.source_corner(raw)
        struct.pack_into('<I',raw,corner+3*32+12,1)
        self.assertEqual(read_hctp_with_weights(raw)['triangle_count'],1)

    def test_vif_fixed_address_with_implicit_groups(self):
        groups = [dict(source_vertex_start=0,vertex_count=2,source_bones=[0]),
                  dict(source_vertex_start=2,vertex_count=2,source_bones=[0,1])]
        weights, report = decode_weight_packets(self.raw('weights-offset.vif'),0,3,4,groups)
        self.assertEqual(weights, [[(0,1.)],[(0,1.)],[(0,.25),(1,.75)],[(0,.5),(1,.5)]])
        self.assertEqual(report['implicit_rigid_vertices'],2)

    def test_psp_known_layout_aliases_and_answer(self):
        model = audit_yobj(self.raw('psp-quad.yobj'))
        report = model['report']
        self.assertEqual([report[k] for k in ('meshes','vertices','triangles','bones','textures','indices')],
                         [1,4,2,2,1,4])
        mesh = model['meshes'][0]
        self.assertEqual(mesh['stride'],44)
        self.assertEqual(mesh['stored_bone_palette'],[1,2])
        self.assertEqual(mesh['materials'][0]['triangles'],[(0,1,2),(1,3,2)])
        self.assertEqual([v['weights'] for v in mesh['vertices']],
                         [[1,0],[.25,.75],[.5,.5],[0,1]])
        self.assertEqual((report['mesh_reports'][0]['vertex_buffer_start']-8)%16,0)

    def test_psp_invalid_index_palette_weight_and_alias(self):
        source = self.raw('psp-quad.yobj')
        audit = audit_yobj(source)
        mesh = struct.unpack_from('<I',source,36)[0]+8
        palette = struct.unpack_from('<I',source,mesh+8)[0]+8
        material = struct.unpack_from('<I',source,mesh+12)[0]+8
        vp = audit['report']['mesh_reports'][0]['vertex_buffer_start']
        ip = audit['report']['mesh_reports'][0]['submeshes'][0]['index_ranges'][0]['start']
        mutations = [(ip,'H',4),(palette+16,'I',3),(vp,'f',2),
                     (material+140,'I',ip-8+4),(36,'I',0xfffffff0)]
        for address,fmt,value in mutations:
            with self.subTest(address=address):
                raw = bytearray(source); struct.pack_into('<'+fmt,raw,address,value)
                with self.assertRaises((ValueError,FormatError)):
                    audit_yobj(raw)

    def test_pof0_all_widths_known_hex(self):
        # Field locations have successive deltas 4,256,65536 bytes.
        self.assertEqual(encode_relocations([12,268,65804]).hex(),'418040c0004000')
        encoded = bytes.fromhex('418040c0004000')
        raw = bytearray(65808)
        struct.pack_into('<I',raw,4,65800)
        raw += b'POF0' + struct.pack('<I',len(encoded)) + encoded
        self.assertEqual(relocations(raw),[12,268,65804])

    def test_bpe_literal_and_pair_known_answers(self):
        for name in ('literal.bpe','pair.bpe'):
            self.assertEqual(decompress(self.raw(name)),b'ABAB!')
        raw = bytearray(self.raw('pair.bpe'))
        struct.pack_into('<I',raw,12,4)
        with self.assertRaises(ValueError):
            decompress(raw)

    def test_pac_relative_origin_alignment_and_preserved_unknown(self):
        raw = self.raw('psp-quad.pac')
        report = inspect_pac(raw)
        self.assertEqual([s['id'] for s in report['sections']],[2,9,50])
        self.assertEqual(len(raw)%2048,0)
        for s in report['sections']:
            self.assertEqual(s['offset']%16,0)
        model = report['sections'][0]
        self.assertEqual(decompress(raw[model['offset']:model['offset']+model['size']]),
                         self.raw('psp-quad.yobj'))
        after = replace_sections(raw,{2:self.raw('psp-quad.yobj')})
        def payloads(data):
            return {s['id']:data[s['offset']:s['offset']+s['size']]
                    for s in inspect_pac(data)['sections']}
        self.assertEqual(payloads(raw)[50],b'opaque-preserve')
        self.assertEqual(payloads(after)[50],payloads(raw)[50])
        self.assertEqual(payloads(after)[9],payloads(raw)[9])

    def test_ps2_nibbles_alpha_and_written_gim_known_answers(self):
        from app.ps2_textures import read_rtx3
        from tools.texture_convert import read_gim
        rgba, _ = read_rtx3(self.raw('skin-t4.rtx3'))
        self.assertEqual(rgba[0,:4,0].tolist(),[0,16,128,240])
        self.assertEqual(rgba[0,:4,3].tolist(),[0,127,255,255])
        indices, colors = read_gim(self.raw('skin-t4.gim'))
        self.assertEqual(indices.shape,(8,32))
        self.assertEqual(indices[0,:16].tolist(),list(range(16)))
        self.assertEqual(colors[:2,3].tolist(),[0,127])
        self.assertEqual(len(self.raw('skin-t4.gim')),272+32*8//2)


if __name__=='__main__':
    unittest.main()
