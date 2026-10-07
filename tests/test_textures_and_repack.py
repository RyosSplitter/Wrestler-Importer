from collections import Counter
import struct
import unittest

import numpy as np

from tools.pac_inspect import FormatError, inspect_pac
from tools.pac_repack import replace_sections
from tools.stripify import stripify
from tools.texture_convert import budget_texture, read_gim, read_gim4, read_gim8, read_rtx3, write_gim4, write_gim8
from tools.yobj_alignment import align_yobj_pof0


def canonical(triangle):
    a, b, c = triangle
    return min((a, b, c), (b, c, a), (c, a, b))


class TextureAndRepackTests(unittest.TestCase):
    def test_indexed4_nibble_order_swizzle_and_alpha_roundtrip(self):
        indices = (np.arange(64 * 16).reshape(16, 64) + np.arange(16)[:, None]).astype(np.uint8) % 16
        palette = np.arange(64, dtype=np.uint8).reshape(16, 4)
        palette[0, 3], palette[15, 3] = 0, 255
        encoded = write_gim4(indices, palette)
        self.assertEqual(encoded[128], 0x10)
        self.assertEqual(encoded[144], 0x21)  # Next row within the first 16-byte x 8-row tile.
        self.assertEqual(encoded[256], 0x10)  # First row of the second tile.
        pixels, colors = read_gim(encoded)
        np.testing.assert_array_equal(pixels, indices)
        np.testing.assert_array_equal(colors, palette)
        with self.assertRaises(FormatError):
            read_gim4(encoded[:-1])
        with self.assertRaises(FormatError):
            write_gim4(indices[:, :16], palette)

    def test_texture_budget_reduces_dimensions_and_preserves_transparency(self):
        indices = np.zeros((64, 128), dtype=np.uint8)
        indices[:, 64:] = 1
        palette = np.zeros((256, 4), dtype=np.uint8)
        palette[1] = [220, 30, 10, 255]
        pixels, colors = budget_texture(indices, palette, 64, 4)
        self.assertEqual(pixels.shape, (32, 64))
        self.assertEqual(colors.shape, (16, 4))
        self.assertIn(0, colors[pixels][:, :, 3])
        self.assertIn(255, colors[pixels][:, :, 3])
        self.assertLessEqual(int(pixels.max()), 15)

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

    def test_odd_sized_model_and_unaligned_table_keep_payloads_on_aligned_addresses(self):
        # A two-entry PAC has a 24-byte table; align absolute, not relative offsets.
        payloads = [(2, b'YOBJ' + bytes(39)), (8, b'original opaque bytes')]
        table = bytearray(b'PAC ' + struct.pack('<I', 2))
        offset = 0
        for sid, payload in payloads:
            table += struct.pack('<H', sid) + offset.to_bytes(3, 'little') + len(payload).to_bytes(3, 'little')
            offset += len(payload)
        original = bytes(table) + b''.join(p for _, p in payloads)
        replacement = b'YOBJ' + bytes(45)
        after = replace_sections(original, {2: replacement})
        sections = inspect_pac(after)['sections']
        for section, expected in zip(sections, [replacement, payloads[1][1]]):
            self.assertEqual(section['offset'] % 16, 0)
            self.assertEqual(section['size'], len(expected))
            self.assertEqual(after[section['offset']:section['offset'] + section['size']], expected)

    def test_relocation_padding_is_included_in_chunk_size(self):
        model = bytearray(b'YOBJ' + bytes(28))
        struct.pack_into('<I', model, 4, 24)
        original = bytes(model) + b'POF0' + struct.pack('<I', 3) + b'ABC'
        aligned = align_yobj_pof0(original)
        self.assertEqual(len(aligned), 48)
        self.assertEqual(aligned[:36], original[:36])
        self.assertEqual(struct.unpack_from('<I', aligned, 36)[0], 8)
        self.assertEqual(aligned[40:], b'ABC' + bytes(5))
        self.assertEqual(align_yobj_pof0(aligned), aligned)
        for damaged in [original[:-1], original + b'\0', b'NOPE' + original[4:]]:
            with self.assertRaises(ValueError):
                align_yobj_pof0(damaged)


if __name__ == '__main__':
    unittest.main()
