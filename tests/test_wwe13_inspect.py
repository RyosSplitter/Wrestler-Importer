"""Procedural, game-asset-free conformance checks for the research reader."""
import struct
import tempfile
import unittest
from pathlib import Path
import zlib

from tools.pac_inspect import FormatError
from tools.wwe13_inspect import expand_zlib, inspect, read_jboy, read_pach


def wrapper(raw):
    stream = zlib.compress(raw)
    result = b'ZLIB' + struct.pack('<3I', 0x1230, len(stream), len(raw)) + stream
    return result + bytes((-len(result)) % 4)


def model_fixture():
    data = bytearray(768)
    data[:4] = b'JBOY'
    struct.pack_into('>I', data, 4, len(data) - 8)
    struct.pack_into('>7I', data, 24, 1, 64, 1, 1, 536, 616, 632)
    a = 72
    struct.pack_into('>4I', data, a, 3, 1, 1, 1)
    struct.pack_into('>I', data, a + 92, 1)
    struct.pack_into('>4I', data, a + 104, 256, 392, 416, 440)
    struct.pack_into('>I', data, a + 120, 42)  # NOT a texture index.
    data[a + 124:a + 131] = b'yCh_foo'
    struct.pack_into('>I', data, a + 156, 476)
    struct.pack_into('>I', data, 264, 272)
    for i, pos in enumerate(((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))):
        struct.pack_into('>6f4B', data, 280 + i * 28, *pos, 0., 0., 1., 255, 255, 255, 255)
        struct.pack_into('>4Bf', data, 400 + i * 8, 0, 0, 0, 0, 1.)
    struct.pack_into('>3I', data, 484, 0x06000000, 3, 504)
    struct.pack_into('>3H', data, 512, 0, 1, 2)
    data[544:550] = b'vector'
    struct.pack_into('>i', data, 544 + 48, -1)
    data[624:629] = b'color'
    data[640:645] = b'trial'
    return bytes(data) + b'POF0'


class TestWwe13Research(unittest.TestCase):
    def test_lossless_wrapper_and_padding(self):
        raw = b'abc' * 100
        self.assertEqual(expand_zlib(wrapper(raw)), raw)

    def test_wrong_expansion_size_rejected(self):
        data = bytearray(wrapper(b'hello'))
        struct.pack_into('<I', data, 12, 4)
        with self.assertRaises(FormatError):
            expand_zlib(data)

    def test_truncated_stream_rejected(self):
        with self.assertRaises(FormatError):
            expand_zlib(wrapper(b'hello')[:18])

    def test_nonzero_padding_rejected(self):
        with self.assertRaises(FormatError):
            expand_zlib(wrapper(b'hello') + b'x')

    def test_declared_expansion_bound(self):
        data = bytearray(wrapper(b'hi'))
        struct.pack_into('<I', data, 12, 128 * 1024 * 1024)
        with self.assertRaises(FormatError):
            expand_zlib(data)

    def test_model_geometry_and_metadata(self):
        model = read_jboy(model_fixture())
        self.assertEqual(model['vertex_count'], 3)
        self.assertEqual(model['provisional_strip_triangle_count'], 1)
        self.assertEqual(model['trailing_bytes'], 4)
        self.assertEqual(model['meshes'][0]['materials'][0]['material_id_raw'], 42)
        self.assertEqual(model['meshes'][0]['vertices'][1]['position'], [1., 0., 0.])

    def test_bad_vertex_index_rejected(self):
        data = bytearray(model_fixture())
        struct.pack_into('>H', data, 516, 3)
        with self.assertRaises(FormatError):
            read_jboy(data)

    def test_invalid_weight_sum_rejected(self):
        data = bytearray(model_fixture())
        struct.pack_into('>f', data, 404, .5)
        with self.assertRaises(FormatError):
            read_jboy(data)

    def test_invalid_active_palette_slot_rejected(self):
        data = bytearray(model_fixture())
        data[400] = 1
        with self.assertRaises(FormatError):
            read_jboy(data)

    def test_significant_sentinel_rejected(self):
        data = bytearray(model_fixture())
        data[400] = 255
        with self.assertRaises(FormatError):
            read_jboy(data)

    def test_tiny_sentinel_residual_preserved_without_normalizing(self):
        data = bytearray(model_fixture())
        struct.pack_into('>I', data, 72 + 92, 3)
        struct.pack_into('>I', data, 72 + 108, 664)
        for i in range(3):
            for j, (slot, weight) in enumerate(((0, .6), (0, .4), (255, -2e-8))):
                struct.pack_into('>4Bf', data, 672 + (i * 3 + j) * 8, slot, 0, 0, 0, weight)
        model = read_jboy(data)
        records = model['meshes'][0]['vertices'][0]['raw_influences']
        self.assertEqual(records[2]['palette_slot'], 255)
        self.assertEqual(records[2]['raw_weight'], struct.unpack('>f', struct.pack('>f', -2e-8))[0])
        self.assertEqual(model['unused_weight_records'], 3)

    def test_bone_cycle_rejected(self):
        data = bytearray(model_fixture())
        struct.pack_into('>i', data, 592, 0)
        with self.assertRaises(FormatError):
            read_jboy(data)

    def test_outside_declared_model_rejected(self):
        data = bytearray(model_fixture())
        struct.pack_into('>I', data, 72 + 108, 768)
        with self.assertRaises(FormatError):
            read_jboy(data)

    def test_pach_overlap_rejected(self):
        packed = wrapper(b'test')
        data = b'PACH' + struct.pack('<I6I', 2, 0, 0, len(packed), 1, 0, len(packed)) + packed
        with self.assertRaises(FormatError):
            read_pach(data, 0)

    def test_epac_inventory_new_output_only(self):
        payload = wrapper(model_fixture())
        pach = b'PACH' + struct.pack('<4I', 1, 0, 0, len(payload)) + payload
        source = b'EPAC' + bytes(2044) + pach
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'inspection'
            report = inspect(source, path)
            self.assertEqual(len(report['bundles']), 1)
            self.assertEqual(report['bundles'][0]['sections'][0]['model']['bone_count'], 1)
            with self.assertRaises(FileExistsError):
                inspect(source, path)


if __name__ == '__main__':
    unittest.main()
