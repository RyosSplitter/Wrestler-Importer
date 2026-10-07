"""Experimental HCTP PS2 geometry decoder for the supplied 0900.pac layout.

This reads geometry and texture coordinates, not PS2 skinning or texture pixels.
Other PS2 games and packet variants are unsupported.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

try:
    from .pac_inspect import FormatError, inspect_pac
    from .yobj_read import Reader, _finite, read_yobj, write_obj
except ImportError:
    from pac_inspect import FormatError, inspect_pac
    from yobj_read import Reader, _finite, read_yobj, write_obj


def read_hctp(data: bytes) -> dict:
    model = read_yobj(data)
    r = Reader(data)
    r.limit = model["declared_end"]
    mesh_start = r.u32(36) + 8
    meshes, positions = [], []
    raw_vertex_total = 0
    for mi in range(model["mesh_count"]):
        a = mesh_start + mi * 64
        group_count, material_count, group_ptr, material_ptr = r.unpack("<4I", a)
        count = r.u32(a + 40)
        if r.u32(a + 32) != count * 2 + 2:
            raise FormatError("Unsupported HCTP position/normal packet count")
        raw_vertex_total += count
        r.check(group_ptr + 8, group_count * 32)
        raw_vertices = []
        groups = []
        for gi in range(group_count):
            vertex_count, bone_count, pos_ptr, normal_ptr = r.unpack("<4I", group_ptr + 8 + gi * 32)
            if not 1 <= bone_count <= 4:
                raise FormatError("Unsupported HCTP group bone count")
            bones = r.unpack("<" + "I" * bone_count, group_ptr + 24 + gi * 32)
            if any(b >= model["bone_count"] for b in bones):
                raise FormatError("HCTP group bone reference is out of range")
            r.check(pos_ptr + 8, vertex_count * 16)
            r.check(normal_ptr + 8, vertex_count * 16)
            start = len(raw_vertices)
            for vi in range(vertex_count):
                position = r.unpack("<4f", pos_ptr + 8 + vi * 16)
                normal = r.unpack("<4f", normal_ptr + 8 + vi * 16)
                _finite((*position, *normal))
                if abs(position[3] - 1) > 0.001:
                    raise FormatError("Unsupported HCTP position vector convention")
                raw_vertices.append({"position": position[:3], "normal": normal[:3],
                                     "source_vertex_index": start + vi,
                                     "uv": (0, 0), "color": (255, 255, 255, 255),
                                     "weights": []})
                positions.append(position[:3])
            groups.append({"source_vertex_start": start, "vertex_count": vertex_count,
                           "source_bones": bones})
        if len(raw_vertices) != count:
            raise FormatError("HCTP group vertex counts differ from mesh count")
        r.check(material_ptr + 8, material_count * 208)
        # UVs live on strip corners, not in the source position array. Keep
        # seams by splitting an index when UV/color differs across corners.
        vertices = copy.deepcopy(raw_vertices)
        corner_map = {}
        assigned = set()
        materials = []
        for mati in range(material_count):
            ma = material_ptr + 8 + mati * 208
            texture_id = r.u32(ma + 40)
            if texture_id >= model["texture_count"]:
                raise FormatError("HCTP material texture reference is out of range")
            strip_count, strip_ptr = r.unpack("<2I", ma + 196)
            r.check(strip_ptr + 8, strip_count * 16)
            strips, triangles = [], []
            for si in range(strip_count):
                primitive, attributes, corner_count, corner_ptr = r.unpack("<4I", strip_ptr + 8 + si * 16)
                if (primitive, attributes) != (3, 3):
                    raise FormatError("Unsupported HCTP draw packet")
                r.check(corner_ptr + 8, corner_count * 32)
                strip = []
                for ci in range(corner_count):
                    ca = corner_ptr + 8 + ci * 32
                    uvq = r.unpack("<3f", ca)
                    source_index = r.u32(ca + 12)
                    color_float = r.unpack("<4f", ca + 16)
                    _finite((*uvq, *color_float))
                    if source_index >= count or abs(uvq[2] - 1) > 0.001:
                        raise FormatError("Unsupported HCTP corner index or UV convention")
                    if any(c < 0 or c > 1 for c in color_float):
                        raise FormatError("Unsupported HCTP corner color")
                    key = (source_index, uvq[:2], color_float)
                    if key not in corner_map:
                        v = copy.deepcopy(raw_vertices[source_index])
                        v["uv"] = uvq[:2]
                        v["color"] = tuple(round(c * 255) for c in color_float)
                        v["source_color"] = color_float
                        if source_index not in assigned:
                            index = source_index
                            vertices[index] = v
                            assigned.add(source_index)
                        else:
                            index = len(vertices)
                            vertices.append(v)
                        corner_map[key] = index
                    strip.append(corner_map[key])
                strips.append(strip)
                for ti in range(max(0, len(strip) - 2)):
                    tri = (strip[ti], strip[ti + 2], strip[ti + 1]) if ti % 2 else tuple(strip[ti:ti + 3])
                    # A repeated source position index is a strip degenerate,
                    # even when distinct UVs created separate output vertices.
                    if len({vertices[v]["source_vertex_index"] for v in tri}) == 3:
                        triangles.append(tri)
            materials.append({"texture_id": texture_id, "strips": strips, "triangles": triangles})
        meshes.append({"index": mi, "bone_palette": [], "source_groups": groups,
                       "vertices": vertices, "materials": materials,
                       "source_vertex_count": count})
    model.update(geometry_decoded=True, meshes=meshes, geometry_layout="hctp_ps2_experimental",
                 source_skinning_decoded=False, source_vertex_count=raw_vertex_total,
                 vertex_count=sum(len(m["vertices"]) for m in meshes),
                 triangle_count=sum(len(mat["triangles"]) for m in meshes for mat in m["materials"]))
    if positions:
        model["bounds"] = {"min": [min(p[k] for p in positions) for k in range(3)],
                           "max": [max(p[k] for p in positions) for k in range(3)]}
    model["warnings"].append("Experimental geometry decode: validate shape, winding and UVs against the original game/importer before conversion")
    return model


def load_hctp(path: Path) -> dict:
    data = path.read_bytes()
    if data.startswith(b"PAC "):
        report = inspect_pac(data)
        sections = [s for s in report["sections"] if s["kind"] == "model_section"]
        if len(sections) != 1:
            raise FormatError("Expected one HCTP model section")
        s = sections[0]
        data = data[s["offset"]:s["offset"] + s["size"]]
    return read_hctp(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--obj", type=Path)
    args = parser.parse_args()
    try:
        model = load_hctp(args.model)
        for output in (args.json, args.obj):
            if output and output.exists():
                raise FileExistsError(f"Refusing to overwrite {output}")
        if args.json:
            with args.json.open("x", encoding="utf-8") as f:
                json.dump(model, f, indent=2, allow_nan=False)
                f.write("\n")
        if args.obj:
            write_obj(model, args.obj)
        print(json.dumps({k: v for k, v in model.items() if k not in ("meshes", "bones")}, indent=2))
    except (OSError, FormatError) as exc:
        print(f"HCTP decode failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
