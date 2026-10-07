import struct
import unittest

from tools.hctp_read import read_hctp
from tools.pac_inspect import FormatError


def sample():
    d = bytearray(848)
    d[:4] = b"YOBJ"
    struct.pack_into("<I", d, 4, 840)
    struct.pack_into("<7I", d, 24, 1, 2, 1, 64, 648, 808, 824)
    struct.pack_into("<4I", d, 72, 1, 1, 128, 296)
    struct.pack_into("<I", d, 104, 10)
    struct.pack_into("<I", d, 112, 4)
    struct.pack_into("<4I4i", d, 136, 4, 1, 168, 232, 1, -1, -1, -1)
    positions = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0))
    for i, p in enumerate(positions):
        struct.pack_into("<4f", d, 176 + i * 16, *p, 1)
        struct.pack_into("<4f", d, 240 + i * 16, 0, 0, 1, 0)
    struct.pack_into("<2I", d, 500, 1, 504)
    struct.pack_into("<4I", d, 512, 3, 3, 4, 520)
    for i, p in enumerate(positions):
        struct.pack_into("<3fI4f", d, 528 + i * 32, p[0], p[1], 1, i, 1, 1, 1, 1)
    for i, name in enumerate((b"root", b"child")):
        a = 656 + i * 80
        d[a:a + len(name)] = name
        struct.pack_into("<f", d, a + 28, 1)
        struct.pack_into("<i", d, a + 48, i - 1)
    d[816:820] = b"skin"
    d[832:836] = b"test"
    return d


class HctpTests(unittest.TestCase):
    def test_positions_normals_uvs_and_triangles(self):
        model = read_hctp(bytes(sample()))
        self.assertEqual(model["source_vertex_count"], 4)
        self.assertEqual(model["vertex_count"], 4)
        self.assertEqual(model["triangle_count"], 2)
        self.assertFalse(model["source_skinning_decoded"])
        mesh = model["meshes"][0]
        self.assertEqual(mesh["vertices"][3]["uv"], (1, 1))
        self.assertEqual(mesh["vertices"][3]["position"], (1, 1, 0))
        self.assertEqual(mesh["materials"][0]["triangles"], [(0, 1, 2), (1, 3, 2)])

    def test_uv_seams_split_without_moving_source_vertex(self):
        d = sample()
        struct.pack_into("<I", d, 636, 0)
        model = read_hctp(bytes(d))
        self.assertEqual(model["vertex_count"], 5)
        a, b = model["meshes"][0]["vertices"][0], model["meshes"][0]["vertices"][4]
        self.assertEqual(a["position"], b["position"])
        self.assertNotEqual(a["uv"], b["uv"])

    def test_degenerate_uses_original_indices_despite_uv_split(self):
        d = sample()
        struct.pack_into("<I", d, 604, 1)
        self.assertEqual(read_hctp(bytes(d))["triangle_count"], 0)

    def test_unknown_packets_bad_corners_and_ranges_rejected(self):
        for offset, value in ((512, 4), (540, 100), (144, 100000), (500, 10000), (104, 999)):
            d = sample()
            struct.pack_into("<I", d, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                read_hctp(bytes(d))


if __name__ == "__main__":
    unittest.main()
