"""WWE SVR PSP PAC/YOBJ static preview for Noesis. Version 0.1.0.

Self-contained: Python standard library + Noesis, no extraction utilities.
Reads verified PSP GE vertex layouts, native strips, UVs and indexed GIMs.
Does not edit files, guess PS2 layouts, repair geometry or sanitize away alpha.
Bone/weight records are validated, but animation/export rigging is not provided.
"""
import math
import os
import struct
import traceback

try:
    from inc_noesis import *
except ImportError:
    # The pure readers are also exercised by independent repository tests.
    pass

MAX_BYTES = 64 * 1024 * 1024


class Reader:
    def __init__(self, data, limit=None):
        self.data = data
        self.limit = len(data) if limit is None else limit
        if self.limit > len(data) or self.limit < 0:
            raise ValueError("Invalid data limit")

    def span(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.limit:
            raise ValueError("Data range outside allocation: %d + %d / %d" % (offset, size, self.limit))
        return self.data[offset:offset + size]

    def unpack(self, fmt, offset):
        return struct.unpack(fmt, self.span(offset, struct.calcsize(fmt)))

    def u32(self, offset):
        return self.unpack('<I', offset)[0]

    def pointer(self, offset):
        target = self.u32(offset) + 8
        self.span(target, 0)
        if target % 4:
            raise ValueError("Unaligned YOBJ pointer")
        return target

    def name(self, offset):
        return self.span(offset, 16).split(b'\0', 1)[0].decode('cp932', 'replace')


def decompress(data):
    """Bounded Yukes BPE 0x100 dictionary expansion; no subprocess/temp files."""
    if data[:4] != b'BPE ':
        return data
    r = Reader(data)
    version, packed, expected = r.unpack('<3I', 4)
    if version != 0x100 or packed + 16 != len(data) or expected > MAX_BYTES:
        raise ValueError("Unsupported BPE header/size")
    cursor = 16
    output = bytearray()
    while cursor < len(data):
        left, right = list(range(256)), [0] * 256
        index = 0
        while index < 256:
            count = r.span(cursor, 1)[0]; cursor += 1
            if count > 127:
                index += count - 127
                count = 0
            if index > 256:
                raise ValueError("BPE dictionary skip overflow")
            if index == 256:
                break
            for unused in range(count + 1):
                if index >= 256:
                    raise ValueError("BPE dictionary run overflow")
                left[index] = r.span(cursor, 1)[0]; cursor += 1
                if left[index] != index:
                    right[index] = r.span(cursor, 1)[0]; cursor += 1
                index += 1
        cache, active = {}, set()
        def expand(symbol):
            if symbol in cache:
                return cache[symbol]
            if left[symbol] == symbol:
                value = bytes(bytearray([symbol]))
            else:
                if symbol in active:
                    raise ValueError("Cyclic BPE dictionary")
                active.add(symbol)
                a, b = expand(left[symbol]), expand(right[symbol])
                if len(a) + len(b) > expected - len(output):
                    raise ValueError("BPE expansion exceeds declared output")
                value = a + b
                active.remove(symbol)
            cache[symbol] = value
            return value
        for symbol in range(256):
            expand(symbol)
        length = r.unpack('<H', cursor)[0]; cursor += 2
        if not length:
            raise ValueError("Empty BPE block")
        tokens = r.span(cursor, length); cursor += length
        for symbol in tokens:
            value = cache[symbol]
            if len(output) + len(value) > expected:
                raise ValueError("BPE output overflow")
            output.extend(value)
    if len(output) != expected:
        raise ValueError("BPE output length mismatch")
    return bytes(output)


def parse_pac(data):
    r = Reader(data)
    if data[:4] != b'PAC ' or len(data) > MAX_BYTES:
        raise ValueError("Not a supported costume PAC")
    count = r.u32(4)
    if not 1 <= count <= 4096:
        raise ValueError("Invalid PAC section count")
    origin = 8 + 8 * count
    r.span(8, 8 * count)
    rows = []
    for i in range(count):
        raw = r.span(8 + 8 * i, 8)
        section = struct.unpack('<H', raw[:2])[0]
        offset = origin + int.from_bytes(raw[2:5], 'little')
        size = int.from_bytes(raw[5:8], 'little')
        if offset < origin or not size:
            raise ValueError("Invalid PAC entry")
        rows.append((section, offset, size))
    previous = origin
    for section, offset, size in sorted(rows, key=lambda x: x[1]):
        r.span(offset, size)
        if offset < previous:
            raise ValueError("Overlapping PAC entries")
        previous = offset + size
    return [(section, decompress(r.span(offset, size))) for section, offset, size in rows]


def parse_texture_table(data):
    r = Reader(data)
    count, marker, reserved, offset = r.unpack('<4I', 0)
    if marker != 256 or reserved != 0 or offset != 16 or not 1 <= count <= 4096:
        raise ValueError("Unsupported named texture table")
    r.span(16, count * 32)
    rows = []
    for i in range(count):
        a = 16 + i * 32
        size, start = r.unpack('<2I', a + 20)
        if start < 16 + count * 32 or not size:
            raise ValueError("Invalid texture allocation")
        rows.append((r.name(a), start, size))
    previous = 16 + count * 32
    for name, start, size in sorted(rows, key=lambda x: x[1]):
        r.span(start, size)
        if start < previous:
            raise ValueError("Overlapping texture entries")
        previous = start + size
    return [(name, r.span(start, size)) for name, start, size in rows]


def parse_yobj(data):
    if data[:4] != b'YOBJ' or len(data) > MAX_BYTES:
        raise ValueError("Missing PSP YOBJ")
    r = Reader(data)
    end = r.u32(4) + 8
    if end < 72 or r.u32(12) + 8 != end:
        raise ValueError("Invalid PSP YOBJ size")
    r = Reader(data, end)
    meshes, bones, textures = r.unpack('<3I', 24)
    if meshes > 4096 or bones > 4096 or textures > 4096 or not meshes:
        raise ValueError("Unreasonable YOBJ counts")
    mesh_start, bone_start, texture_start, name_start = [r.pointer(i) for i in (36, 40, 44, 48)]
    r.span(mesh_start, 64 * meshes); r.span(bone_start, 80 * bones); r.span(texture_start, 16 * textures)
    parents = []
    for i in range(bones):
        a = bone_start + 80 * i
        parent = r.unpack('<i', a + 48)[0]
        if not -1 <= parent < bones:
            raise ValueError("Bone parent outside skeleton")
        parents.append(parent)
    complete = set()
    for i in range(bones):
        chain = set()
        while i != -1 and i not in complete:
            if i in chain:
                raise ValueError("Cyclic skeleton")
            chain.add(i); i = parents[i]
        complete.update(chain)
    names = [r.name(texture_start + 16 * i) for i in range(textures)]
    result = []
    for i in range(meshes):
        a = mesh_start + 64 * i
        material_count, vertex_count, flag = r.u32(a + 4), r.u32(a + 40), r.u32(a + 28)
        palette_start, material_start, cell = [r.pointer(a + j) for j in (8, 12, 24)]
        palette_count = r.u32(palette_start + 4)
        if palette_count > 4096 or r.u32(palette_start) != vertex_count:
            raise ValueError("Invalid mesh palette header")
        vertex_start = r.pointer(cell)
        if r.pointer(palette_start + 8) != vertex_start:
            raise ValueError("Vertex pointer aliases disagree")
        palette = [x - 1 for x in r.unpack('<' + 'I' * palette_count, palette_start + 16)]
        if any(x < 0 or x >= bones for x in palette) or len(set(palette)) != len(palette):
            raise ValueError("Bone palette outside skeleton")
        base = flag & ~0x1C000
        if flag == 0x11FF:
            slots, width, fmt, denominator = 0, 0, '', 1
        elif base in (0x17FF, 0x13FF, 0x15FF):
            slots = ((flag >> 14) & 7) + 1
            if slots != palette_count:
                raise ValueError("Palette size and weight slots disagree")
            width, fmt, denominator = {0x17FF: (4, 'f', 1), 0x13FF: (1, 'B', 128), 0x15FF: (2, 'H', 32768)}[base]
        else:
            raise ValueError("Unsupported PSP vertex flag 0x%x (PS2 is a different layout)" % flag)
        weight_bytes = ((slots * width + 3) // 4) * 4
        stride = 36 + weight_bytes
        raw = r.span(vertex_start, vertex_count * stride)
        vertices = []
        for vi in range(vertex_count):
            va = vertex_start + stride * vi
            weights = [w / denominator for w in r.unpack('<' + fmt * slots, va)] if slots else []
            uv = r.unpack('<2f', va + weight_bytes)
            color = r.unpack('<4B', va + weight_bytes + 8)
            normal = r.unpack('<3f', va + weight_bytes + 12)
            position = r.unpack('<3f', va + weight_bytes + 24)
            if not all(math.isfinite(x) for x in tuple(weights) + uv + normal + position):
                raise ValueError("Non-finite vertex attributes")
            if any(w < 0 or w > 1.0001 for w in weights) or (slots and abs(sum(weights) - 1) > .001):
                raise ValueError("Invalid/unnormalized PSP weights")
            vertices.append(dict(position=position, normal=normal, uv=uv, color=color, weights=weights))
        r.span(material_start, material_count * 144)
        materials = []
        for j in range(material_count):
            ma = material_start + 144 * j
            tid = r.unpack('<H', ma + 22)[0]
            if tid >= textures:
                raise ValueError("Material texture index out of range")
            strip_count, strip_start = r.u32(ma + 132), r.pointer(ma + 136)
            first_indices = r.pointer(ma + 140)
            r.span(strip_start, strip_count * 16)
            triangles, strips = [], []
            for k in range(strip_count):
                sa = strip_start + 16 * k
                length, ip = r.u32(sa + 8), r.pointer(sa + 12)
                if not 1 <= length <= 65535:
                    raise ValueError("Invalid triangle strip count")
                if k == 0 and ip != first_indices:
                    raise ValueError("First index pointer alias mismatch")
                values = r.unpack('<' + 'H' * length, ip)
                if any(v >= vertex_count for v in values):
                    raise ValueError("Index outside its vertex buffer")
                for n in range(length - 2):
                    tri = (values[n], values[n + 2], values[n + 1]) if n % 2 else values[n:n + 3]
                    if len(set(tri)) == 3:
                        triangles.append(tuple(tri))
                strips.append(values)
            materials.append(dict(texture_id=tid, triangles=triangles, strips=strips))
        result.append(dict(index=i, vertices=vertices, materials=materials, stride=stride,
                           bone_palette=palette, weight_slots=slots, flag=flag))
    return dict(name=r.name(name_start), texture_names=names, meshes=result, bone_count=bones)


def decode_gim(data):
    """Observed PSP indexed4/indexed8 swizzled GIM, including narrow padded rows."""
    r = Reader(data)
    if data[:12] != b'MIG.00.1PSP\0' or r.u32(20) + 16 != len(data):
        raise ValueError("Invalid GIM header/length")
    fmt, order, w, h, bits = r.unpack('<5H', 68)
    if (fmt, bits) not in ((4, 4), (5, 8)) or order != 1 or not w or not h or w & (w - 1) or h & (h - 1):
        raise ValueError("Unsupported GIM pixel format")
    if w > 4096 or h > 4096:
        raise ValueError("GIM dimensions exceed preview limit")
    pitch = ((w * bits + 7) // 8 + 15) // 16 * 16
    ph = (h + 7) // 8 * 8
    start, end = 64 + r.u32(92), 48 + r.u32(52)
    if start != 128 or end != start + pitch * ph or 64 + r.u32(96) != end:
        raise ValueError("GIM pixel bounds mismatch")
    if r.unpack('<5H', end + 20) != (3, 0, 1 << bits, 1, 32):
        raise ValueError("Unsupported GIM CLUT")
    if end + 80 + (1 << bits) * 4 != len(data) or end + r.u32(end + 4) != len(data):
        raise ValueError("GIM palette bounds mismatch")
    if r.unpack('<4H', 104) != (1, 1, 3, 1):
        raise ValueError("Unsupported GIM levels/frames")
    palette = r.span(end + 80, (1 << bits) * 4)
    packed = r.span(start, pitch * ph)
    rgba = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            bx = x if bits == 8 else x // 2
            address = ((y // 8) * (pitch // 16) + bx // 16) * 128 + (y % 8) * 16 + bx % 16
            value = packed[address]
            index = value if bits == 8 else (value >> (4 * (x % 2))) & 15
            pixel = 4 * (y * w + x)
            rgba[pixel:pixel + 4] = palette[index * 4:index * 4 + 4]
    return w, h, bytes(rgba)


def read_scene(data):
    data = decompress(data)
    if data[:4] == b'YOBJ':
        return [(2, parse_yobj(data))], {}
    entries = parse_pac(data)
    models = [(section, parse_yobj(raw)) for section, raw in entries if raw[:4] == b'YOBJ']
    if not models:
        raise ValueError("No supported PSP YOBJ in this PAC")
    # Costume table takes precedence over separately retained effect tables.
    images = {}
    for section, raw in sorted(entries, key=lambda x: x[0] == 9):
        if len(raw) >= 16 and raw[4:16] == struct.pack('<3I', 256, 0, 16):
            for name, blob in parse_texture_table(raw):
                if blob[:12] == b'MIG.00.1PSP\0':
                    images[name.lower()] = decode_gim(blob)
    return sorted(models, key=lambda x: (x[0] != 2, x[0])), images


def check_type(data):
    try:
        read_scene(data)
        return 1
    except (ValueError, struct.error, OverflowError, RuntimeError):
        return 0


def registerNoesisTypes():
    handle = noesis.register('WWE SVR PSP PAC / YOBJ', '.pac;.yobj;.bpe')
    noesis.setHandlerTypeCheck(handle, check_type)
    noesis.setHandlerLoadModel(handle, load_model)
    noesis.addOption(handle, '-pspmainonly', 'Show only main PAC section 2 (hide accessories/alternate models).', 0)
    return 1


def _external_texture(folder, name):
    # Asset names are metadata, never trusted path components.
    if not name or os.path.basename(name) != name or any(c in name for c in '/\\:'):
        return None
    for ext in ('.gim', '.png', '.dds'):
        path = os.path.join(folder, name + ext)
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Sibling texture exceeds preview size limit')
        if ext == '.gim':
            w, h, rgba = decode_gim(raw)
            return NoeTexture(name, w, h, rgba, noesis.NOESISTEX_RGBA32)
        return rapi.loadTexByHandler(raw, ext)
    return None


def load_model(data, mdl_list):
    try:
        models, images = read_scene(data)
        if noesis.optWasInvoked('-pspmainonly'):
            models = [m for m in models if m[0] == 2]
        if not models:
            raise ValueError('No main section 2 model')
        ctx = rapi.rpgCreateContext()
        textures, materials, material_names = [], [], {}
        folder = rapi.getDirForFilePath(rapi.getInputName())
        for section, model in models:
            for name in model['texture_names']:
                key = name.lower()
                if key in material_names:
                    continue
                texture = None
                if key in images:
                    w, h, rgba = images[key]
                    texture = NoeTexture(name, w, h, rgba, noesis.NOESISTEX_RGBA32)
                else:
                    texture = _external_texture(folder, name)
                if texture is not None:
                    texture.name = name
                    textures.append(texture)
                else:
                    print('WWE PSP: missing texture ' + name + ' (standalone YOBJ needs matching GIM/PNG files)')
                mat = NoeMaterial(name, name if texture is not None else '')
                # Do not force double-sided drawing or alter alpha samples to
                # hide a model defect. Cutout alpha remains in the RGBA pixels.
                if key in images and any(a < 128 for a in images[key][2][3::4]):
                    mat.setAlphaTest(.5)
                materials.append(mat); material_names[key] = name
            for mesh in model['meshes']:
                positions, normals, uvs, colors = bytearray(), bytearray(), bytearray(), bytearray()
                for vertex in mesh['vertices']:
                    # Proper rotation, identical to the existing native OBJ
                    # preview; no scale, reshaping, V flip or winding reversal.
                    x, y, z = vertex['position']; positions.extend(struct.pack('<3f', x, z, -y))
                    x, y, z = vertex['normal']; normals.extend(struct.pack('<3f', x, z, -y))
                    uvs.extend(struct.pack('<2f', *vertex['uv']))
                    colors.extend(bytes(bytearray(vertex['color'])))
                rapi.rpgBindPositionBuffer(bytes(positions), noesis.RPGEODATA_FLOAT, 12)
                rapi.rpgBindNormalBuffer(bytes(normals), noesis.RPGEODATA_FLOAT, 12)
                rapi.rpgBindUV1Buffer(bytes(uvs), noesis.RPGEODATA_FLOAT, 8)
                rapi.rpgBindColorBufferOfs(bytes(colors), noesis.RPGEODATA_UBYTE, 4, 0, 4)
                for j, material in enumerate(mesh['materials']):
                    if not material['triangles']:
                        continue
                    indices = bytearray()
                    for tri in material['triangles']:
                        indices.extend(struct.pack('<3I', *tri))
                    rapi.rpgSetName('section_%d_mesh_%d_material_%d' % (section, mesh['index'], j))
                    rapi.rpgSetMaterial(material_names[model['texture_names'][material['texture_id']].lower()])
                    rapi.rpgCommitTriangles(bytes(indices), noesis.RPGEODATA_INT, len(indices) // 4, noesis.RPGEO_TRIANGLE, 1)
                rapi.rpgClearBufferBinds()
        mdl = rapi.rpgConstructModel()
        if mdl is None:
            raise ValueError('No renderable triangles')
        mdl.setModelMaterials(NoeModelMaterials(textures, materials))
        mdl_list.append(mdl)
        print('WWE PSP: loaded %d YOBJ model(s), %d texture(s); native rest geometry, no animation emulation.' % (len(models), len(textures)))
        return 1
    except Exception:
        noesis.logPopup()
        print('WWE PSP preview failed:')
        traceback.print_exc()
        return 0
