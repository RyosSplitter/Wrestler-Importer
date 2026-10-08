"""Exercise packet addressing, implicit groups and malformed input rejection."""
import struct
import unittest

from tools.hctp_weights import decode_weight_packets
from tools.pac_inspect import FormatError


class HctpWeightsTests(unittest.TestCase):
    def fixture(self):
        # Six source vertices: rigid 0..1, blended 2..3, rigid 4, blended 5.
        groups = [dict(source_vertex_start=0, vertex_count=2, source_bones=[3]),
                  dict(source_vertex_start=2, vertex_count=2, source_bones=[3, 4]),
                  dict(source_vertex_start=4, vertex_count=1, source_bones=[4]),
                  dict(source_vertex_start=5, vertex_count=1, source_bones=[3, 4, 7])]
        first = struct.pack('<4I', 0, 0, 0, 0x6C020282)
        second = struct.pack('<4I', 0, 0, 0, 0x6C010285)
        data = first + struct.pack('<8f', .25, .75, 0, 0, .5, .5, 0, 0)
        data += second + struct.pack('<4f', .25, .25, .5, 0)
        return bytearray(data), groups

    def decode(self, data, groups):
        return decode_weight_packets(data, 0, len(data)//16, 6, groups)

    def test_fixed_vu_address_and_implicit_weights(self):
        data, groups = self.fixture()
        weights, report = self.decode(data, groups)
        self.assertEqual(weights[0], [(3, 1.0)])
        self.assertEqual(weights[2], [(3, .25), (4, .75)])
        self.assertEqual(weights[5], [(3, .25), (4, .25), (7, .5)])
        self.assertEqual(report['explicit_vertices'], 3)
        self.assertEqual(report['implicit_rigid_vertices'], 3)

    def test_malformed_streams_are_rejected(self):
        for change in ('overlap', 'address', 'nan', 'unused', 'sum', 'command', 'truncated'):
            with self.subTest(change=change):
                data, groups = self.fixture()
                if change == 'overlap': struct.pack_into('<I', data, 60, 0x6C010282)
                elif change == 'address': struct.pack_into('<I', data, 12, 0x6C02027F)
                elif change == 'nan': struct.pack_into('<f', data, 16, float('nan'))
                elif change == 'unused': struct.pack_into('<f', data, 24, .1)
                elif change == 'sum': struct.pack_into('<f', data, 16, .5)
                elif change == 'command': struct.pack_into('<I', data, 12, 0x64020282)
                elif change == 'truncated': del data[-16:]
                with self.assertRaises(FormatError): self.decode(data, groups)

    def test_group_coverage_is_required(self):
        data, groups = self.fixture()
        with self.assertRaises(FormatError): self.decode(data, groups[:-1])
        groups[1]['source_vertex_start'] = 1
        with self.assertRaises(FormatError): self.decode(data, groups)


if __name__ == '__main__':
    unittest.main()
