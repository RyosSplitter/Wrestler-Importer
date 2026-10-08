"""PS2 source textures: nibble order, palettes, color depth, alpha and GIM."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np
from PIL import Image

from app.ps2_textures import convert_pac, read_rtx3, read_source
from stable_pipeline.pac_inspect import FormatError
from stable_pipeline.texture_convert import read_gim, read_rtx3 as original_rtx3
from tests.test_yobj_read import sample


def rtx(psm, pixels, palette=b'', *, cpsm=0, csm=0, csa=0, width=32, height=8):
    header = bytearray(64)
    header[:4] = b'RTX3'
    struct.pack_into('<I', header, 4, 56 + len(pixels) + len(palette))
    tex0 = ((psm << 20) | ((width.bit_length()-1) << 26) |
            ((height.bit_length()-1) << 30) | (cpsm << 51) | (csm << 55) | (csa << 56))
    struct.pack_into('<Q', header, 8, tex0)
    struct.pack_into('<2I', header, 36, len(pixels), 56)
    return bytes(header) + pixels + palette


def pac(image):
    model = sample()
    textures = (struct.pack('<4I', 1, 0x100, 0, 16) + b'skin'.ljust(16, b'\0') +
                b'txc\0' + struct.pack('<3I', len(image), 48, 0) + image)
    header = b'PAC ' + struct.pack('<I', 2)
    offset = 0
    for sid, payload in ((2, model), (9, textures)):
        header += struct.pack('<H', sid) + offset.to_bytes(3, 'little') + len(payload).to_bytes(3, 'little')
        offset += len(payload)
    return header + model + textures


class Ps2TextureTests(unittest.TestCase):
    def test_psmt4_low_nibble_first_compact_palette_and_alpha(self):
        palette = np.zeros((16, 4), dtype=np.uint8)
        palette[:, 0] = np.arange(16) * 16
        palette[:, 3] = 128
        palette[0, 3], palette[1, 3] = 0, 64
        rgba, details = read_rtx3(rtx(20, bytes([0x10, 0xF8])*64, palette.tobytes()))
        self.assertEqual(details['format'], 'PSMT4')
        self.assertEqual(rgba[0, :4, 0].tolist(), [0, 16, 128, 240])
        self.assertEqual(rgba[0, :4, 3].tolist(), [0, 127, 255, 255])

    def test_psmt8_matches_original_reader_exactly(self):
        pixels = np.arange(256, dtype=np.uint8).reshape(8, 32)
        palette = np.arange(1024, dtype=np.uint16).astype(np.uint8).reshape(256, 4)
        data = rtx(19, pixels.tobytes(), palette.tobytes())
        indices, colors = original_rtx3(data)
        rgba, _ = read_rtx3(data)
        np.testing.assert_array_equal(rgba, colors[indices])

    def test_psmt4_full_palette_selects_csm1_bank(self):
        palette = np.zeros((256, 4), dtype=np.uint8)
        palette[:, 0] = np.arange(256)
        palette[:, 3] = 128
        rgba, _ = read_rtx3(rtx(20, bytes([0xF8])*128, palette.tobytes(), csa=1))
        self.assertEqual(rgba[0, :2, 0].tolist(), [24, 31])
        with self.assertRaisesRegex(FormatError, 'CLUT bank'):
            read_rtx3(rtx(20, bytes(128), palette.tobytes(), csa=16))

    def test_psmt8_csm2_palette_has_no_address_swap(self):
        palette = np.zeros((256, 4), dtype=np.uint8)
        palette[:, 0], palette[:, 3] = np.arange(256), 128
        rgba, _ = read_rtx3(rtx(19, bytes([8, 16])*128, palette.tobytes(), csm=1))
        self.assertEqual(rgba[0, :2, 0].tolist(), [8, 16])

    def test_rgb5a1_palette_and_direct_color(self):
        words = struct.pack('<4H', 0x801F, 0x83E0, 0xFC00, 0x7FFF)
        expected = [[255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255], [255, 255, 255, 0]]
        for fmt in (2, 10):
            with self.subTest(fmt=fmt):
                direct, _ = read_rtx3(rtx(fmt, words*64))
                self.assertEqual(direct[0, :4].tolist(), expected)
                indexed, _ = read_rtx3(rtx(20, bytes([0x10, 0x32])*64, words*4, cpsm=fmt))
                self.assertEqual(indexed[0, :4].tolist(), expected)

    def test_direct_rgba32_uses_ps2_alpha_range(self):
        rgba, _ = read_rtx3(rtx(0, bytes([20, 40, 60, 64, 100, 120, 140, 128])*128))
        self.assertEqual(rgba[0, :2].tolist(), [[20, 40, 60, 127], [100, 120, 140, 255]])

    def test_direct_rgb24_is_opaque_in_both_upload_layouts(self):
        for pixels in (bytes([10, 20, 30])*256, bytes([10, 20, 30, 0])*256):
            rgba, _ = read_rtx3(rtx(1, pixels))
            self.assertEqual(rgba[0, 0].tolist(), [10, 20, 30, 255])

    def test_malformed_sizes_and_unknown_formats_report_registers(self):
        for data, message in ((rtx(20, bytes(127), bytes(64)), 'indexed pixel layout'),
                              (rtx(20, bytes(128), bytes(60)), 'palette size'),
                              (rtx(19, bytes(256), bytes(1024), cpsm=1), 'palette color format'),
                              (rtx(63, bytes(256)), 'PSM 63')):
            with self.subTest(message=message), self.assertRaisesRegex(FormatError, message):
                read_rtx3(data)

    def test_psmt4_pac_to_gim_and_png_keeps_cutout_alpha(self):
        palette = np.zeros((16, 4), dtype=np.uint8)
        palette[1] = [160, 80, 40, 128]
        data = pac(rtx(20, bytes([0x10])*128, palette.tobytes()))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / '1800.pac'
            output = Path(folder) / 'textures'
            source.write_bytes(data)
            manifest = convert_pac(source, output)
            entry = manifest['textures'][0]
            pixels, colors = read_gim((output / entry['gim']).read_bytes())
            expected = np.tile(np.array([[0, 0, 0, 0], [160, 80, 40, 255]], dtype=np.uint8), (8, 16, 1))
            np.testing.assert_array_equal(colors[pixels], expected)
            np.testing.assert_array_equal(np.array(Image.open(output / entry['png'])), expected)
            self.assertEqual(entry['source_format']['format'], 'PSMT4')
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual(json.loads((output/'textures.json').read_text())['color_depth'], 4)

    def test_error_names_the_source_texture_and_pac_section(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / '1800.pac'
            source.write_bytes(pac(rtx(63, bytes(256))))
            with self.assertRaisesRegex(FormatError, 'skin.*1800.pac.*section 9.*PSM 63'):
                read_source(source)


if __name__ == '__main__':
    unittest.main()
