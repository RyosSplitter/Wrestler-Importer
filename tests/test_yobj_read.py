import struct
import tempfile
import unittest
from pathlib import Path

from tools.pac_inspect import FormatError
from tools.yobj_read import compare_skeletons, read_yobj, write_obj


def sample():
    """Four vertices, a two-triangle strip, and a root/child skeleton."""
    d = bytearray(712)
    d[:4] = b"YOBJ"
    struct.pack_into("<I", d, 4, 704)
    struct.pack_into("<7I", d, 24, 1, 2, 1, 64, 512, 672, 688)
    struct.pack_into("<3I", d, 76, 1, 128, 344)
    struct.pack_into("<2I", d, 96, 152, 0x57FF)
    struct.pack_into("<I", d, 112, 4)
    struct.pack_into("<I", d, 140, 2)
    struct.pack_into("<2I", d, 152, 1, 2)
    struct.pack_into("<I", d, 160, 168)
    positions = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0))
    for j, pos in enumerate(positions):
        a = 176 + j * 44
        struct.pack_into("<4f", d, a, 0.25, 0.75, pos[0], pos[1])
        struct.pack_into("<4B", d, a + 16, 255, 255, 255, 255)
        struct.pack_into("<6f", d, a + 20, 0, 0, 1, *pos)
    struct.pack_into("<2I", d, 484, 1, 488)
    struct.pack_into("<2I", d, 504, 4, 504)
    struct.pack_into("<4H", d, 512, 0, 1, 2, 3)
    for j, name in enumerate((b"root", b"child")):
        a = 520 + j * 80
        d[a:a + len(name)] = name
        struct.pack_into("<f", d, a + 28, 1)
        struct.pack_into("<i", d, a + 48, j - 1)
    d[680:684] = b"skin"
    d[696:700] = b"test"
    return d


class YobjTests(unittest.TestCase):
    def test_ge_integer_weight_alignment_matches_float_geometry(self):
        for flag, packed in ((0x53FF, bytes([32, 96, 0, 0])),
                             (0x55FF, struct.pack('<2H', 8192, 24576))):
            d = sample()
            expected = read_yobj(bytes(d), psp_geometry=True)
            records = [bytes(d[176+j*44:176+(j+1)*44]) for j in range(4)]
            struct.pack_into('<I', d, 100, flag)
            for j, record in enumerate(records):
                start = 176+j*40
                d[start:start+40] = packed + record[8:]
            actual = read_yobj(bytes(d), psp_geometry=True)
            self.assertEqual(actual['meshes'][0]['vertices'], expected['meshes'][0]['vertices'])
            self.assertEqual(actual['meshes'][0]['materials'], expected['meshes'][0]['materials'])
            self.assertEqual(actual['weight_sum_outliers'], 0)

    def test_geometry_weights_and_strip_winding(self):
        m = read_yobj(bytes(sample()), psp_geometry=True)
        self.assertEqual(m["vertex_count"], 4)
        self.assertEqual(m["triangle_count"], 2)
        self.assertEqual(m["weight_sum_outliers"], 0)
        self.assertEqual(m["meshes"][0]["vertices"][0]["weights"], (0.25, 0.75))
        self.assertEqual(m["meshes"][0]["materials"][0]["triangles"], [(0, 1, 2), (1, 3, 2)])
        self.assertEqual(m["bones"][1]["parent"], 0)
        self.assertEqual(m["meshes"][0]["bone_palette"], (0, 1))
        self.assertEqual(m["meshes"][0]["stored_bone_palette"], (1, 2))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "model.obj"
            write_obj(m, p)
            text = p.read_text()
            self.assertIn("f 1/1/1 2/2/2 3/3/3", text)
            self.assertIn("f 2/2/2 4/4/4 3/3/3", text)
            with self.assertRaises(FileExistsError):
                write_obj(m, p)

    def test_ps2_flag_rejected_but_skeleton_still_readable(self):
        d = sample()
        struct.pack_into("<I", d, 100, 0x1870)
        self.assertEqual(read_yobj(bytes(d))["bone_count"], 2)
        with self.assertRaisesRegex(FormatError, "Unsupported PSP vertex flag"):
            read_yobj(bytes(d), psp_geometry=True)

    def test_corrupt_offsets_faces_and_coordinates_rejected(self):
        for offset, fmt, value in ((4, "<I", 90000), (40, "<I", 90000),
                                   (512, "<H", 40), (208, "<f", float("nan"))):
            d = sample()
            struct.pack_into(fmt, d, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                read_yobj(bytes(d), psp_geometry=True)

    def test_bone_cycle_rejected(self):
        d = sample()
        struct.pack_into("<i", d, 568, 1)
        with self.assertRaisesRegex(FormatError, "Cycle"):
            read_yobj(bytes(d))

    def test_outside_palette_influences_retained_and_reported(self):
        d = sample()
        struct.pack_into("<I", d, 156, 3)
        m = read_yobj(bytes(d), psp_geometry=True)
        self.assertEqual(m["vertices_with_outside_bone_influences"], 4)
        self.assertEqual(m["meshes"][0]["bone_palette"], (0, 2))
        self.assertEqual(len(m["warnings"]), 1)

    def test_comparison_uses_names_rather_than_indices(self):
        ref = {"bones": [{"index": 0, "name": "root", "parent": -1},
                         {"index": 1, "name": "child", "parent": 0}]}
        target = {"bones": [{"index": 0, "name": "child", "parent": 1},
                            {"index": 1, "name": "root", "parent": -1}]}
        comparison = compare_skeletons(ref, target)
        self.assertEqual(comparison["different_parents"], [])
        self.assertEqual(comparison["different_indices"], ["child", "root"])


if __name__ == "__main__":
    unittest.main()
