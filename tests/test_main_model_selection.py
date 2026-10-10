"""Synthetic multi-YOBJ PAC regressions, without distributing game assets."""
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from app.ps2_textures import read_source
from desktop.adapters.hctp import HctpAdapter
from model_qa.geometry import read_model
from stable_pipeline.pac_inspect import FormatError as TextureFormatError
from tests.test_ps2_textures import rtx
from tools.generate_conformance_fixtures import pac, vectors
from tools.hctp_read import load_hctp, read_hctp
from tools.hctp_weights import load_hctp_with_weights, read_hctp_with_weights
from tools.pac_inspect import FormatError, inspect_pac, select_model_section
from tools.yobj_read import load_model, read_yobj


def texture_table():
    palette = np.zeros((16, 4), dtype=np.uint8)
    palette[1] = (160, 80, 40, 128)
    image = rtx(20, bytes([0x10])*128, palette.tobytes())
    # Auxiliary-only images deliberately have an unsupported payload. They
    # must not be decoded when they are not referenced by the section-2 model.
    other = b'UNSUPPORTED AUXILIARY TEXTURE'
    offset = 16+2*32
    table = struct.pack('<4I', 2, 0x100, 0, 16)
    for name, payload in (('skin', image), ('aux_only', other)):
        table += name.encode().ljust(16, b'\0')+b'txc\0'+struct.pack('<3I', len(payload), offset, 0)
        offset += len(payload)
    return table+image+other


class MainModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.main = vectors()['hctp-quad.yobj']
        aux = bytearray(self.main)
        texture_offset = struct.unpack_from('<I', aux, 44)[0]+8
        aux[texture_offset:texture_offset+16] = b'aux_only'.ljust(16, b'\0')
        self.aux = bytes(aux)

    def test_all_source_readers_select_main_even_when_auxiliaries_come_first(self):
        for section_list in (
            [(2, self.main), (6, self.aux), (7, self.aux)],
            [(7, self.aux), (6, self.aux), (2, self.main)],
        ):
            with self.subTest(order=[s for s, r in section_list]), tempfile.TemporaryDirectory() as folder:
                data = pac(section_list+[(9, texture_table()), (50, b'unchanged unrelated data')])
                source = Path(folder)/'custom.pac';source.write_bytes(data)
                self.assertEqual(load_model(source), read_yobj(self.main))
                self.assertEqual(load_hctp(source), read_hctp(self.main))
                expected = read_hctp_with_weights(self.main)
                self.assertEqual(load_hctp_with_weights(source), expected)
                self.assertEqual(read_model(source, source=True), expected)
                actual, images = HctpAdapter().read(source)
                self.assertEqual(actual, expected)
                self.assertEqual([name for _, name, *_ in images], ['skin'])
                self.assertEqual(images[0][3][0, :2].tolist(), [[0, 0, 0, 0], [160, 80, 40, 255]])
                self.assertEqual(source.read_bytes(), data)

    def test_additional_yobj_does_not_need_main_model_decoder_support(self):
        # Only the outer container range and signature of the ignored section
        # are inspected; it is not parsed as another wrestler or combined.
        data = pac([(6, b'YOBJunknown auxiliary layout'), (2, self.main)])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'custom.pac';source.write_bytes(data)
            self.assertEqual(load_hctp_with_weights(source), read_hctp_with_weights(self.main))

    def test_duplicate_primary_and_ambiguous_or_missing_primary_are_rejected(self):
        cases = [
            [(2, self.main), (2, self.main), (6, self.aux)],
            [(6, self.aux), (7, self.aux)],
            [(2, b'NOT A MODEL'), (6, self.aux)],
            [(9, texture_table())],
        ]
        for sections in cases:
            with self.subTest(ids=[s for s, r in sections]):
                with self.assertRaises(FormatError):select_model_section(inspect_pac(pac(sections)))

    def test_corrupt_primary_is_not_replaced_with_a_valid_auxiliary(self):
        data = pac([(2, b'YOBJtruncated'), (6, self.aux)])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'custom.pac';source.write_bytes(data)
            with self.assertRaisesRegex(FormatError, 'truncated'):load_hctp_with_weights(source)
            with self.assertRaises(TextureFormatError):read_source(source)

    def test_bad_auxiliary_range_is_still_rejected_by_container_validation(self):
        data = bytearray(pac([(2, self.main), (6, self.aux)]))
        data[18:21] = (0xFFFFFF).to_bytes(3, 'little')
        with self.assertRaises(FormatError):inspect_pac(bytes(data))

    def test_existing_single_model_and_raw_yobj_inputs_are_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'model.pac'
            for data in (self.main, pac([(2, self.main)]), pac([(42, self.main)])):
                source.write_bytes(data)
                self.assertEqual(load_hctp_with_weights(source), read_hctp_with_weights(self.main))
                self.assertEqual(load_model(source), read_yobj(self.main))


if __name__ == '__main__':
    unittest.main()
