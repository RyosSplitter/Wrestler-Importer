import struct
import tempfile
import unittest
from pathlib import Path

from tools.pac_inspect import FormatError, extract_pac, inspect_pac


def pac(payloads):
    table = bytearray(b"PAC " + struct.pack("<I", len(payloads)))
    offset = 0
    for sid, payload in payloads:
        table += sid.to_bytes(2, "little") + offset.to_bytes(3, "little") + len(payload).to_bytes(3, "little")
        offset += len(payload)
    return bytes(table) + b"".join(p for _, p in payloads) + bytes(8)


def texture_table(name=b"example", offset=48):
    image = b"MIG.00.1PSP\0" + bytes(20)
    row = name.ljust(16, b"\0") + b"gim\0" + struct.pack("<III", len(image), offset, 0)
    return struct.pack("<4I", 1, 0x100, 0, 16) + row + image


class PacTests(unittest.TestCase):
    def test_exact_extraction_and_original_preservation(self):
        model = b"YOBJ" + bytes(48)
        textures = texture_table(name=b"../../escape")
        data = pac([(2, model), (9, textures)])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            report = extract_pac(data, output)
            self.assertEqual(report["section_count"], 2)
            self.assertEqual(report["trailing_bytes"], 8)
            self.assertEqual((output / report["sections"][0]["file"]).read_bytes(), model)
            entry = report["sections"][1]["textures"][0]
            self.assertEqual((output / entry["file"]).read_bytes(), textures[48:])
            self.assertFalse((Path(tmp) / "escape").exists())
            with self.assertRaises(FileExistsError):
                extract_pac(data, output)
            self.assertEqual(data, pac([(2, model), (9, textures)]))

    def test_bad_header_count_and_truncation(self):
        for data in (b"", b"NOPE" + bytes(4), b"PAC " + struct.pack("<I", 100),
                     pac([(2, b"YOBJ" + bytes(48))])[:25]):
            with self.subTest(data=data), self.assertRaises(FormatError):
                inspect_pac(data)

    def test_overlapping_sections(self):
        data = bytearray(pac([(2, b"YOBJ" + bytes(48)), (8, bytes(16))]))
        data[18:21] = bytes(3)
        with self.assertRaises(FormatError):
            inspect_pac(bytes(data))

    def test_texture_cannot_point_into_table_or_outside_section(self):
        for offset in (0, 10000):
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                inspect_pac(pac([(9, texture_table(offset=offset))]))

    def test_unknown_sections_are_preserved_and_reported(self):
        report = inspect_pac(pac([(50, b"unsupported")]))
        self.assertEqual(report["sections"][0]["kind"], "unknown")
        self.assertEqual(len(report["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
