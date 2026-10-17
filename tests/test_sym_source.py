"""Asset-free byte fixtures for the observed SYM reader contracts."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from tests.test_pac_inspect import pac
from tools.pac_inspect import FormatError
from tools.sym_ch_study import study
from tools.sym_source import read_atlas, read_ch_directory, sha


def archive(ids=(0, 0x101)):
    payload = pac([(50, b'unknown data retained')]).ljust(256, b'\0')
    data = bytearray(0x4000+2048*len(ids))
    data[:4] = b'DPAC'
    struct.pack_into('<3I', data, 4, 8+4*len(ids), 2048*len(ids), 7)
    data[0x800:0x804] = b'EMD '
    struct.pack_into('<HH', data, 0x804, 0x8000|len(ids), 0)
    for i, ident in enumerate(ids):
        struct.pack_into('<HH', data, 0x808+4*i, ident, 1)
        a = 0x4000+2048*i
        data[a:a+256] = payload
        data[a+2044:a+2048] = b'\x12\x34\x56\x78'
    return bytes(data)


def atlas(bits=8):
    colors = 1 << bits
    pixels = bytes(range(32)) if bits == 8 else bytes((0x21, 0x43))*8
    palette = b''.join(bytes((i, 255-i, i//2, (0, 64, 128)[i%3])) for i in range(colors))
    tex0 = ({8: 19, 4: 20}[bits] << 20) | (3 << 26) | (2 << 30)
    picture = struct.pack('<IIIHH4BHH', 48+len(pixels)+len(palette), len(palette),
        len(pixels), 48, colors, 0, 1, 3, 5 if bits == 8 else 4, 8, 4)+struct.pack('<Q', tex0)+bytes(16)
    return b'TIM2'+struct.pack('<BBH', 4, 0, 1)+bytes(8)+picture+pixels+palette


class DirectoryTests(unittest.TestCase):
    def test_allocation_arithmetic_and_unknown_trailers_preserved(self):
        source = archive()
        result = read_ch_directory(source)
        self.assertEqual(result['payload_offset'], 0x4000)
        self.assertEqual(result['entry_count'], 2)
        self.assertEqual(result['entries'][1]['offset'], 0x4800)
        self.assertEqual(result['entries'][1]['id_hex'], '0101')
        entry = result['entries'][0]
        self.assertEqual(entry['gap_bytes'], 1792)
        self.assertEqual(entry['allocation_trailer_hex'], '12345678')
        self.assertEqual(entry['gap_nonzero_bytes'], 4)
        self.assertEqual(entry['sha256'], sha(source[0x4000:0x4100]))
        self.assertFalse(result['conversion_supported'])

    def test_rejects_unsupported_or_inconsistent_directory(self):
        mutations = ((0x804, '<H', 2), (4, '<I', 999), (8, '<I', 2049),
            (0x806, '<H', 1), (0x80c, '<H', 0), (0x80e, '<H', 65535),
            (0x80a, '<H', 0))
        for offset, fmt, value in mutations:
            raw = bytearray(archive())
            struct.pack_into(fmt, raw, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                read_ch_directory(bytes(raw))
        for raw in (b'', archive()[:-1], b'NOPE'+archive()[4:]):
            with self.assertRaises(FormatError):
                read_ch_directory(raw)

    def test_readonly_exact_extraction_and_deterministic_report(self):
        raw = archive()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'ch.pac'
            source.write_bytes(raw)
            a = study(source, root/'a', extract=True)
            b = study(source, root/'b', extract=True)
            self.assertEqual(a, b)
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual((root/'a/extracted/0000.pac').read_bytes(), raw[0x4000:0x4100])
            self.assertEqual((root/'a/extracted/0000.allocation-gap.bin').read_bytes(), raw[0x4100:0x4800])
            self.assertEqual(json.loads((root/'a/report.json').read_text()), a)
            with self.assertRaises(FileExistsError):
                study(source, root/'a')


class AtlasTests(unittest.TestCase):
    def test_index8_palette_order_and_alpha_without_source_edit(self):
        raw = atlas()
        before = sha(raw)
        indices, palette, meta = read_atlas(raw)
        np.testing.assert_array_equal(indices.ravel(), np.arange(32))
        self.assertEqual(int(palette[8, 0]), 16)
        self.assertEqual(int(palette[16, 0]), 8)
        self.assertEqual(int(palette[1, 3]), 127)
        self.assertEqual(int(palette[2, 3]), 255)
        self.assertEqual(int(palette[0, 3]), 0)
        self.assertEqual(meta['palette_entries'], 256)
        self.assertFalse(meta['alpha_forced_opaque'])
        self.assertEqual(sha(raw), before)

    def test_index4_low_nibble_first_and_no_clut_permutation(self):
        indices, palette, meta = read_atlas(atlas(4))
        self.assertEqual(indices[0].tolist(), [1, 2, 3, 4, 1, 2, 3, 4])
        np.testing.assert_array_equal(palette[:, 0], np.arange(16))
        self.assertEqual(meta['bits_per_index'], 4)

    def test_rejects_unknown_formats_sizes_and_mips(self):
        for offset, fmt, value in ((5, '<B', 1), (4, '<B', 3),
                (33, '<B', 2), (34, '<B', 0x83), (35, '<B', 3),
                (20, '<I', 40), (28, '<H', 49), (30, '<H', 4), (36, '<H', 65535),
                (40, '<Q', 0), (40, '<Q', (19<<20)|(3<<26)|(2<<30)|(1<<55))):
            raw = bytearray(atlas())
            struct.pack_into(fmt, raw, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                read_atlas(bytes(raw))
        for raw in (atlas()[:-1], atlas()+bytes(16)):
            with self.assertRaises(FormatError):
                read_atlas(raw)


if __name__ == '__main__':
    unittest.main()
