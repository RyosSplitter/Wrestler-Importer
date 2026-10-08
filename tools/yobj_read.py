"""Read YOBJ skeletons and PSP float vertices with float or GE integer weights.

No uploaded editor code is executed or required. Geometry support is explicit:
the HCTP PS2 mesh layout is not handled by the PSP reader.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

try:
    from .pac_inspect import FormatError, inspect_pac
except ImportError:
    from pac_inspect import FormatError, inspect_pac


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.limit = len(data)

    def check(self, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > self.limit:
            raise FormatError(f"YOBJ range outside model: offset={offset}, size={size}")

    def unpack(self, fmt: str, offset: int) -> tuple:
        self.check(offset, struct.calcsize(fmt))
        return struct.unpack_from(fmt, self.data, offset)

    def u32(self, offset: int) -> int:
        return self.unpack("<I", offset)[0]

    def name(self, offset: int) -> str:
        self.check(offset, 16)
        try:
            return self.data[offset:offset + 16].split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as exc:
            raise FormatError("Non-ASCII YOBJ name") from exc


def _finite(values) -> None:
    if any(not math.isfinite(v) for v in values):
        raise FormatError("Non-finite YOBJ coordinate or weight")


def _validate_hierarchy(bones: list[dict]) -> None:
    complete = set()
    for start in range(len(bones)):
        chain = set()
        current = start
        while current != -1 and current not in complete:
            if current in chain:
                raise FormatError("Cycle in YOBJ bone hierarchy")
            chain.add(current)
            current = bones[current]["parent"]
        complete.update(chain)


def read_yobj(data: bytes, *, psp_geometry: bool = False) -> dict:
    r = Reader(data)
    if len(data) < 72 or data[:4] != b"YOBJ":
        raise FormatError("Missing or truncated YOBJ header")
    # Pointer origin is byte 8, rather than the beginning of the file.
    declared_end = r.u32(4) + 8
    if declared_end < 72 or declared_end > len(data):
        raise FormatError("YOBJ declared size is outside input")
    r.limit = declared_end
    mesh_count, bone_count, texture_count, mesh_ptr, bone_ptr, tex_ptr, name_ptr = r.unpack("<7I", 24)
    r.check(mesh_ptr + 8, mesh_count * 64)
    r.check(bone_ptr + 8, bone_count * 80)
    r.check(tex_ptr + 8, texture_count * 16)
    bones = []
    for index in range(bone_count):
        a = bone_ptr + 8 + index * 80
        local = r.unpack("<4f", a + 16)
        rotation = r.unpack("<3f", a + 32)
        global_position = r.unpack("<3f", a + 64)
        _finite((*local, *rotation, *global_position))
        parent = r.unpack("<i", a + 48)[0]
        if parent < -1 or parent >= bone_count:
            raise FormatError("YOBJ parent bone index is out of range")
        bones.append({"index": index, "name": r.name(a), "parent": parent,
                      "local_position": local[:3], "local_w": local[3],
                      "rotation": rotation, "stored_global_position": global_position})
    if len({b["name"] for b in bones}) != len(bones) or any(not b["name"] for b in bones):
        raise FormatError("Empty or duplicate bone names")
    _validate_hierarchy(bones)
    model = {"sha256": hashlib.sha256(data).hexdigest(), "declared_end": declared_end,
             "trailing_bytes": len(data) - declared_end, "mesh_count": mesh_count,
             "bone_count": bone_count, "texture_count": texture_count,
             "model_name": r.name(name_ptr + 8), "bones": bones,
             "textures": [r.name(tex_ptr + 8 + i * 16) for i in range(texture_count)],
             "geometry_decoded": False, "warnings": []}
    if not psp_geometry:
        return model

    meshes = []
    all_positions = []
    for index in range(mesh_count):
        a = mesh_ptr + 8 + index * 64
        material_count, palette_ptr, material_ptr = r.unpack("<3I", a + 4)
        vertex_header_ptr, flag = r.unpack("<2I", a + 24)
        vertex_count = r.u32(a + 40)
        # The original samples use float weights. The region profile uses GE
        # fixed-point integer weights, aligned to four bytes before float UVs.
        base_flag = flag & ~0x1C000
        if base_flag not in (0x17FF, 0x13FF, 0x15FF):
            raise FormatError(f"Unsupported PSP vertex flag 0x{flag:x} in mesh {index}; do not use this decoder for PS2 geometry")
        weight_count = ((flag >> 14) & 7) + 1
        palette_count = r.u32(palette_ptr + 12)
        if palette_count != weight_count:
            raise FormatError("PSP weight slots do not match bone palette")
        stored_palette = r.unpack("<" + "I" * palette_count, palette_ptr + 24)
        # YOBJ mesh references are 1-based; the bone table and parent indices
        # are 0-based. Keeping these distinct is essential for deformation.
        palette = tuple(b - 1 for b in stored_palette)
        outside_palette = [b for b in stored_palette if not 1 <= b <= bone_count]
        if outside_palette:
            model["warnings"].append(
                f"Mesh {index} palette references {outside_palette} outside the declared bone table; game semantics need verification")
        vertex_start = r.u32(vertex_header_ptr + 8) + 8
        weight_width, weight_format, denominator = {
            0x17FF: (4, 'f', 1), 0x13FF: (1, 'B', 128), 0x15FF: (2, 'H', 32768)}[base_flag]
        weight_bytes = 4*((weight_width*weight_count+3)//4)
        stride = 36 + weight_bytes
        r.check(vertex_start, vertex_count * stride)
        vertices = []
        for j in range(vertex_count):
            va = vertex_start + j * stride
            weights = tuple(w/denominator for w in r.unpack('<'+weight_format*weight_count, va))
            uv = r.unpack("<2f", va + weight_bytes)
            color = r.unpack("<4B", va + weight_bytes + 8)
            normal = r.unpack("<3f", va + stride - 24)
            position = r.unpack("<3f", va + stride - 12)
            _finite((*weights, *uv, *normal, *position))
            if any(w < 0 for w in weights):
                raise FormatError("Negative PSP vertex weight")
            vertices.append({"position": position, "normal": normal, "uv": uv,
                             "color": color, "weights": weights})
            all_positions.append(position)
        r.check(material_ptr + 8, material_count * 144)
        materials = []
        for j in range(material_count):
            ma = material_ptr + 8 + j * 144
            texture_id = r.unpack("<H", ma + 22)[0]
            if texture_id >= texture_count:
                raise FormatError("PSP material texture index is out of range")
            strip_count, strip_ptr = r.unpack("<2I", ma + 132)
            r.check(strip_ptr + 8, strip_count * 16)
            strips, triangles = [], []
            for k in range(strip_count):
                count, ptr = r.unpack("<2I", strip_ptr + 16 + k * 16)
                r.check(ptr + 8, count * 2)
                strip = r.unpack("<" + "H" * count, ptr + 8)
                if any(v >= vertex_count for v in strip):
                    raise FormatError("PSP face index is out of range")
                strips.append(strip)
                for t in range(max(0, count - 2)):
                    tri = (strip[t], strip[t + 2], strip[t + 1]) if t % 2 else strip[t:t + 3]
                    if len(set(tri)) == 3:
                        triangles.append(tri)
            materials.append({"texture_id": texture_id, "control": r.u32(ma + 24),
                              "strips": strips, "triangles": triangles})
        meshes.append({"index": index, "flag": flag, "bone_palette": palette,
                       "stored_bone_palette": stored_palette,
                       "vertices": vertices, "materials": materials})
    model.update(geometry_decoded=True, meshes=meshes,
                 vertex_count=len(all_positions),
                 triangle_count=sum(len(mat["triangles"]) for m in meshes for mat in m["materials"]))
    if all_positions:
        model["bounds"] = {"min": [min(p[k] for p in all_positions) for k in range(3)],
                           "max": [max(p[k] for p in all_positions) for k in range(3)]}
    model["weight_sum_outliers"] = sum(abs(sum(v["weights"]) - 1) > 0.001
                                       for m in meshes for v in m["vertices"])
    model["vertices_with_outside_bone_influences"] = sum(
        any((b < 0 or b >= bone_count) and w > 0 for b, w in zip(m["bone_palette"], v["weights"]))
        for m in meshes for v in m["vertices"])
    return model


def load_model(path: Path, *, psp_geometry: bool = False) -> dict:
    data = path.read_bytes()
    if data.startswith(b"PAC "):
        report = inspect_pac(data)
        models = [s for s in report["sections"] if s["kind"] == "model_section"]
        if len(models) != 1:
            raise FormatError("Expected exactly one YOBJ model section in PAC")
        section = models[0]
        data = data[section["offset"]:section["offset"] + section["size"]]
    return read_yobj(data, psp_geometry=psp_geometry)


def compare_skeletons(reference: dict, target: dict) -> dict:
    def entries(model):
        return {b["name"]: (None if b["parent"] == -1 else model["bones"][b["parent"]]["name"])
                for b in model["bones"]}
    ref, dst = entries(reference), entries(target)
    shared = sorted(ref.keys() & dst.keys())
    return {"reference_only": sorted(ref.keys() - dst.keys()),
            "target_only": sorted(dst.keys() - ref.keys()),
            "shared_count": len(shared),
            "different_indices": [n for n in shared
                                  if next(b["index"] for b in reference["bones"] if b["name"] == n)
                                  != next(b["index"] for b in target["bones"] if b["name"] == n)],
            "different_parents": [n for n in shared if ref[n] != dst[n]],
            "note": "Name/parent comparison only; transform and animation compatibility are not established"}


def write_obj(model: dict, output: Path) -> None:
    if not model["geometry_decoded"]:
        raise FormatError("OBJ export requires geometry decoding")
    # Keep raw YOBJ axes, normals, and UVs; no hidden rotation or UV flip.
    with output.open("x", encoding="utf-8") as f:
        f.write("# Raw YOBJ coordinates; geometry preview only; no skeleton or textures\n")
        base = 1
        for mesh in model["meshes"]:
            f.write(f"o mesh_{mesh['index']:02d}\n")
            for v in mesh["vertices"]:
                f.write("v " + " ".join(str(x) for x in v["position"]) + "\n")
            for v in mesh["vertices"]:
                f.write("vt " + " ".join(str(x) for x in v["uv"]) + "\n")
            for v in mesh["vertices"]:
                f.write("vn " + " ".join(str(x) for x in v["normal"]) + "\n")
            for j, material in enumerate(mesh["materials"]):
                f.write(f"g mesh_{mesh['index']:02d}_material_{j:02d}\n")
                for tri in material["triangles"]:
                    f.write("f " + " ".join(f"{base + i}/{base + i}/{base + i}" for i in tri) + "\n")
            base += len(mesh["vertices"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="YOBJ or PAC file")
    parser.add_argument("--psp-geometry", action="store_true")
    parser.add_argument("--json", type=Path, help="Write full decoded data to a NEW file")
    parser.add_argument("--obj", type=Path, help="Write PSP geometry to a NEW OBJ file")
    parser.add_argument("--compare", type=Path, help="Compare this skeleton with another YOBJ/PAC")
    args = parser.parse_args()
    try:
        if args.obj and not args.psp_geometry:
            raise FormatError("--obj requires --psp-geometry")
        model = load_model(args.model, psp_geometry=args.psp_geometry)
        if args.compare:
            model["comparison"] = compare_skeletons(model, load_model(args.compare))
        for output in (args.json, args.obj):
            if output and output.exists():
                raise FileExistsError(f"Refusing to overwrite {output}")
        if args.json:
            with args.json.open("x", encoding="utf-8") as f:
                json.dump(model, f, indent=2, allow_nan=False)
                f.write("\n")
        if args.obj:
            write_obj(model, args.obj)
        summary = {k: v for k, v in model.items() if k not in ("meshes", "bones")}
        print(json.dumps(summary, indent=2, allow_nan=False))
    except (OSError, FormatError) as exc:
        print(f"YOBJ read failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
