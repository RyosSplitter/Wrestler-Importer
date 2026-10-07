from collections import Counter
import struct
import unittest

import numpy as np

from tools.pac_inspect import FormatError, inspect_pac
from tools.pac_repack import replace_sections
from tools.stripify import stripify
from tools.texture_convert import read_gim8, read_rtx3, write_gim8


def canonical(triangle):
    a, b, c = triangle
    return min((a, b, c), (b, c, a), (c, a, b))


class TextureAndRepackTests(unittest.TestCase):
    def test_indexed8_gim_roundtrip_nonuniform_palette_and_pixels(self):
        indices = np.arange(512, dtype=np.uint16).astype(np.uint8).reshape(16, 32)
        palette = np.arange(1024, dtype=np.uint16).astype(np.uint8).reshape(256, 4)
        encoded = write_gim8(indices, palette)
        pixels, colors = read_gim8(encoded)
        np.testing.assert_array_equal(pixels, indices)
        np.testing.assert_array_equal(colors, palette)
        with self.assertRaises(FormatError):
            read_gim8(encoded[:-1])

    def test_rtx3_clut_order_and_ps2_alpha_conversion(self):
        indices = np.arange(512, dtype=np.uint16).astype(np.uint8).reshape(16, 32)
        palette = np.zeros((256, 4), dtype=np.uint8)
        palette[:, 0] = np.arange(256)
        palette[:, 3] = 128
        palette[0, 3] = 64
        d = bytearray(64)
        d[:4] = b'RTX3'
        struct.pack_into('<I', d, 4, 64 + 512 + 1024 - 8)
        struct.pack_into('<Q', d, 8, (19 << 20) | (5 << 26) | (4 << 30))
        struct.pack_into('<2I', d, 36, 512, 56)
        d += indices.tobytes() + palette.tobytes()
        pixels, colors = read_rtx3(bytes(d))
        np.testing.assert_array_equal(pixels, indices)
        self.assertEqual(colors[8, 0], 16)
        self.assertEqual(colors[16, 0], 8)
        self.assertEqual(colors[0, 3], 127)
        self.assertEqual(colors[1, 3], 255)

    def test_psp_swizzle_uses_16_byte_8_row_tiles(self):
        indices = np.arange(512, dtype=np.uint16).astype(np.uint8).reshape(16, 32)
        palette = np.zeros((256, 4), dtype=np.uint8)
        encoded = write_gim8(indices, palette)
        self.assertEqual(encoded[128:144], indices[0, :16].tobytes())
        self.assertEqual(encoded[144:160], indices[1, :16].tobytes())
        self.assertEqual(encoded[256:272], indices[0, 16:].tobytes())

    def test_oriented_stripification_keeps_every_triangle_and_winding(self):
        triangles = [(0, 1, 2), (1, 3, 2), (2, 3, 4), (10, 11, 12)]
        strips = stripify(triangles)
        result = []
        for strip in strips:
            for i in range(len(strip) - 2):
                result.append((strip[i], strip[i + 2], strip[i + 1]) if i % 2 else tuple(strip[i:i + 3]))
        self.assertEqual(Counter(map(canonical, result)), Counter(map(canonical, triangles)))
        self.assertLess(len(strips), len(triangles))

    def test_pac_replacement_preserves_unrelated_sections(self):
        payloads = [(2, b'YOBJ' + bytes(80)), (8, b'untouched base bytes'), (9, b'original textures')]
        table = bytearray(b'PAC ' + struct.pack('<I', 3))
        offset = 0
        for sid, payload in payloads:
            table += sid.to_bytes(2, 'little') + offset.to_bytes(3, 'little') + len(payload).to_bytes(3, 'little')
            offset += len(payload)
        original = bytes(table) + b''.join(p for _, p in payloads)
        after = replace_sections(original, {2: b'YOBJ' + bytes(120), 9: b'new textures'})
        report = inspect_pac(after)
        untouched = next(s for s in report['sections'] if s['id'] == 8)
        self.assertEqual(after[untouched['offset']:untouched['offset'] + untouched['size']], payloads[1][1])
        self.assertEqual(len(after) % 2048, 0)
        with self.assertRaises(FormatError):
            replace_sections(original, {99: b'missing'})


if __name__ == '__main__':
    unittest.main()
