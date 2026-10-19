"""Read-only research inspector for the uploaded ch104 EPAC/PACH/JBOY sample.

Not a converter or a general WWE '13 reader. PACH locations are signature-
discovered and independently validated; the EPAC directory is not yet decoded.
Triangle-strip interpretation and material semantics remain provisional.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zlib

import numpy as np
from PIL import Image

from tools.pac_inspect import FormatError, parse_textures
from tools.yobj_read import _validate_hierarchy

MAX_INPUT = 64 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_TOTAL_EXPANDED = 128 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise FormatError(f'Out-of-bounds research range: {offset}, {size}')
    return data[offset:offset + size]


def unpack(data, fmt, offset):
    return struct.unpack(fmt, checked(data, offset, struct.calcsize(fmt)))


def name(data, offset, size=16):
    return checked(data, offset, size).split(b'\0', 1)[0].decode('ascii')


def expand_zlib(data):
    if checked(data, 0, 4) != b'ZLIB':
        raise FormatError('Expected ZLIB wrapper')
    marker, packed, expanded = unpack(data, '<3I', 4)
    if marker != 0x1230 or not 0 < expanded <= MAX_EXPANDED:
        raise FormatError('Unsupported ZLIB wrapper/expanded size')
    stream = checked(data, 16, packed)
    if any(data[16 + packed:]):
        raise FormatError('Nonzero bytes after declared compressed stream')
    decoder = zlib.decompressobj()
    result = decoder.decompress(stream, expanded + 1)
    if (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or len(result) != expanded):
        raise FormatError('ZLIB stream/declared size mismatch')
    return result


def read_pach(data, start):
    if checked(data, start, 4) != b'PACH':
        raise FormatError('Missing PACH signature')
    count, = unpack(data, '<I', start + 4)
    if not 0 < count <= 4096:
        raise FormatError('Invalid PACH count')
    checked(data, start + 8, count * 12)
    base = start + 8 + count * 12
    rows, end, total, ids = [], base, 0, set()
    for i in range(count):
        ident, relative, size = unpack(data, '<3I', start + 8 + i * 12)
        address = base + relative
        if ident in ids or address < end or address % 4 or not size or size % 4:
            raise FormatError('Unsupported/overlapping PACH records')
        ids.add(ident)
        raw = expand_zlib(checked(data, address, size))
        total += len(raw)
        if total > MAX_TOTAL_EXPANDED:
            raise FormatError('PACH expansion exceeds research bound')
        rows.append(dict(id=ident, offset=address, stored_bytes=size,
                         compressed_bytes=unpack(data, '<I', address + 8)[0],
                         expanded_bytes=len(raw), sha256=sha(raw), raw=raw))
        end = address + size
    return dict(offset=start, payload_origin=base, end=end, sections=rows)


def read_jboy(data):
    """Decode observed BE 184-byte mesh / 80-byte bone records without edits."""
    if checked(data, 0, 4) != b'JBOY':
        raise FormatError('Missing big-endian JBOY signature')
    u = lambda a: unpack(data, '>I', a)[0]
    total_bytes = len(data)
    declared = u(4) + 8
    body = checked(data, 0, declared)
    # All subsequent reads must stay inside declared model, not relocation tail.
    data = body
    meshes_n, mesh_ptr, bones_n, textures_n, bone_ptr, tex_ptr, label_ptr = unpack(data, '>7I', 24)
    checked(data, mesh_ptr + 8, meshes_n * 184)
    checked(data, bone_ptr + 8, bones_n * 80)
    checked(data, tex_ptr + 8, textures_n * 16)
    bones = []
    for i in range(bones_n):
        a = bone_ptr + 8 + i * 80
        parent, = unpack(data, '>i', a + 48)
        if parent < -1 or parent >= bones_n:
            raise FormatError('Invalid source bone parent')
        bones.append(dict(index=i, name=name(data, a), parent=parent,
                          local_position=unpack(data, '>3f', a + 16),
                          rotation=unpack(data, '>3f', a + 32),
                          stored_global_position=unpack(data, '>3f', a + 64)))
    _validate_hierarchy(bones)
    if len({b['name'] for b in bones}) != bones_n:
        raise FormatError('Duplicate bone names')
    meshes, positions = [], []
    sentinel_count, sentinel_max = 0, 0.
    for i in range(meshes_n):
        a = mesh_ptr + 8 + i * 184
        n, draw_count, palette_n = unpack(data, '>3I', a)
        if not 0 < palette_n <= 20:
            raise FormatError('Unsupported embedded palette length')
        palette = unpack(data, '>' + 'I' * palette_n, a + 12)
        if any(not 1 <= b <= bones_n for b in palette):
            raise FormatError('Source palette outside bone table')
        influence_n = u(a + 92)
        if influence_n not in (1, 3, 4):
            raise FormatError('Unobserved source influence layout')
        vh, wp, uvp, tangentp = unpack(data, '>4I', a + 104)
        vp = u(vh + 8) + 8
        wp, uvp, tangentp = wp + 8, uvp + 8, tangentp + 8
        checked(data, vp, n * 28)
        checked(data, wp, n * influence_n * 8)
        checked(data, uvp, n * 8)
        checked(data, tangentp, n * 12)
        pos = np.ndarray((n, 3), dtype='>f4', buffer=data, offset=vp, strides=(28, 4))
        norm = np.ndarray((n, 3), dtype='>f4', buffer=data, offset=vp + 12, strides=(28, 4))
        uv = np.ndarray((n, 2), dtype='>f4', buffer=data, offset=uvp)
        weights = np.ndarray((n, influence_n), dtype='>f4', buffer=data,
                             offset=wp + 4, strides=(influence_n * 8, 8))
        if any(not np.isfinite(v).all() for v in (pos, norm, uv, weights)):
            raise FormatError('Nonfinite vertex attributes')
        if np.max(np.abs(weights.sum(1) - 1)) > 2e-6 or weights.min() < -2e-7:
            raise FormatError('Invalid source weight sums/sign')
        records = []
        for v in range(n):
            row = []
            for j in range(influence_n):
                q = wp + (v * influence_n + j) * 8
                slot = data[q]
                if any(data[q + 1:q + 4]):
                    raise FormatError('Unobserved packed bone-index bytes')
                weight = float(weights[v, j])
                if slot == 255:
                    sentinel_count += 1
                    sentinel_max = max(sentinel_max, abs(weight))
                    if abs(weight) > 2e-7:
                        raise FormatError('Sentinel has significant influence')
                elif slot >= palette_n:
                    raise FormatError('Active index outside source mesh palette')
                row.append(dict(palette_slot=slot, raw_weight=weight))
            # Preserve raw sentinel records; do not average, clamp, or normalize.
            records.append(row)
        # This is not a texture index: hair records can exceed texture count.
        # Preserve it as unknown metadata until shader bindings are decoded.
        material_id_raw = u(a + 120)
        ip = u(a + 156) + 8
        checked(data, ip, draw_count * 12)
        draws, triangles, indices_total = [], [], 0
        for j in range(draw_count):
            primitive, count, pointer = unpack(data, '>3I', ip + j * 12)
            if primitive != 0x06000000:
                raise FormatError('Unobserved draw primitive')
            indices = np.frombuffer(checked(data, pointer + 8, count * 2), dtype='>u2').astype(int).tolist()
            if not indices or max(indices) >= n:
                raise FormatError('Index outside corresponding vertex buffer')
            indices_total += count
            faces = []
            for t in range(count - 2):
                tri = (indices[t], indices[t + 2], indices[t + 1]) if t % 2 else tuple(indices[t:t + 3])
                if len(set(tri)) == 3:
                    faces.append(tri)
            triangles.extend(faces)
            draws.append(dict(primitive_raw=primitive, indices=indices, triangles=faces))
        vertices = [dict(position=pos[v].tolist(), normal=norm[v].tolist(),
                         uv=uv[v].tolist(), color=(255, 255, 255, 255),
                         raw_influences=records[v]) for v in range(n)]
        positions.extend(pos.tolist())
        meshes.append(dict(index=i, vertices=vertices, materials=[dict(material_id_raw=material_id_raw, triangles=triangles)],
                           stored_bone_palette=palette, influence_slots=influence_n,
                           shader=name(data, a + 124), index_count=indices_total,
                           draw_records=draws, vertex_stride=28,
                           weight_stride=influence_n * 8,
                           offsets=dict(vertex=vp, weights=wp, uv=uvp, tangent=tangentp),
                           weight_sum_max_error=float(np.abs(weights.sum(1) - 1).max()),
                           normal_length_max_error=float(np.abs(np.linalg.norm(norm, axis=1) - 1).max())))
    return dict(geometry_decoded=True, mesh_count=meshes_n, bone_count=bones_n,
                texture_count=textures_n, model_label=name(data, label_ptr + 8),
                declared_bytes=declared, trailing_bytes=total_bytes - declared,
                meshes=meshes, bones=bones,
                texture_names=[name(data, tex_ptr + 8 + i * 16) for i in range(textures_n)],
                vertex_count=sum(len(m['vertices']) for m in meshes),
                provisional_strip_triangle_count=sum(len(m['materials'][0]['triangles']) for m in meshes),
                index_count=sum(m['index_count'] for m in meshes),
                bounds=dict(min=np.min(positions, axis=0).tolist(), max=np.max(positions, axis=0).tolist()),
                unused_weight_records=sentinel_count, unused_weight_max_abs=sentinel_max,
                scope='Observed sample only; palette numbering/strip winding/renderer semantics need independent verification')


def texture_inventory(data):
    entries = parse_textures(data)
    for t in entries:
        raw = checked(data, t['offset'], t['size'])
        if raw[:4] != b'DDS ' or unpack(raw, '<I', 4)[0] != 124:
            raise FormatError('Unsupported DDS table image')
        height, width = unpack(raw, '<2I', 12)
        t.update(width=width, height=height, mip_count=unpack(raw, '<I', 28)[0],
                 fourcc=raw[84:88].decode('ascii'), pixel_bits=unpack(raw, '<I', 88)[0],
                 pixel_flags=unpack(raw, '<I', 80)[0])
    return entries


def inspect(data, output):
    if len(data) > MAX_INPUT or checked(data, 0, 4) != b'EPAC':
        raise FormatError('Expected bounded EPAC input')
    output.mkdir(parents=True, exist_ok=False)
    roots = [m.start() for m in re.finditer(b'PACH', data) if m.start() % 2048 == 0]
    if not roots or len(roots) > 64:
        raise FormatError('No bounded aligned PACH candidates')
    report = dict(input_bytes=len(data), sha256=sha(data), container='EPAC',
                  directory_status='UNKNOWN: aligned signature discovery; no general EPAC directory parser', bundles=[])
    previous_end, total = 0, 0
    for i, start in enumerate(roots):
        bundle = read_pach(data, start)
        if start < previous_end:
            raise FormatError('Nested/overlapping discovered PACH bundles')
        previous_end = bundle['end']
        folder = output / f'bundle_{i:02d}'
        folder.mkdir()
        for section in bundle['sections']:
            raw = section.pop('raw')
            total += len(raw)
            if total > MAX_TOTAL_EXPANDED:
                raise FormatError('EPAC expanded total exceeds research bound')
            stem = f"section_{section['id']:05d}"
            (folder / (stem + '.bin')).write_bytes(raw)
            if raw[:4] == b'JBOY':
                model = read_jboy(raw)
                model['trailing_bytes'] = len(raw) - model['declared_bytes']
                (folder / (stem + '-model.json')).write_text(json.dumps(model, indent=2) + '\n')
                section['model'] = {k: v for k, v in model.items() if k != 'meshes'}
                section['mesh_inventory'] = [{k: v for k, v in m.items() if k not in ('vertices', 'draw_records', 'materials')}
                                             | dict(vertex_count=len(m['vertices']), triangle_count=len(m['materials'][0]['triangles']), material_id_raw=m['materials'][0]['material_id_raw']) for m in model['meshes']]
            elif len(raw) >= 16 and raw[4:16] == struct.pack('<3I', 256, 0, 16):
                section['textures'] = texture_inventory(raw)
                for t in section['textures']:
                    texture = checked(raw, t['offset'], t['size'])
                    path = folder / f"{stem}-texture-{t['index']:02d}"
                    path.with_suffix('.dds').write_bytes(texture)
                    try:
                        im = Image.open(io.BytesIO(texture)); im.load(); im.save(path.with_suffix('.png'))
                        t['pillow_decode'] = dict(size=im.size, mode=im.mode)
                    except (OSError, ValueError, NotImplementedError) as exc:
                        t['pillow_decode'] = dict(error=str(exc))
        report['bundles'].append(bundle)
    report['expanded_section_bytes'] = total
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pac', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New local research directory; assets are not redistribution fixtures')
    args = parser.parse_args()
    original = args.pac.read_bytes()
    report = inspect(original, args.output)
    if args.pac.read_bytes() != original:
        raise RuntimeError('Source changed during read-only inspection')
    print(json.dumps(dict(sha256=report['sha256'], input_bytes=len(original), bundles=len(report['bundles']),
                          expanded_bytes=report['expanded_section_bytes'], report=str(args.output / 'report.json')), indent=2))


if __name__ == '__main__':
    main()
