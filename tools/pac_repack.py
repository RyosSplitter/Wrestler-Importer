"""Repack a copy of the observed PSP PAC layout with prepared YOBJ/GIM payloads."""
import argparse
import json
from pathlib import Path
import struct
import sys

try:
    from .pac_inspect import FormatError, inspect_pac
    from .yobj_read import read_yobj
    from .texture_convert import read_gim8
    from .yobj_alignment import align_yobj_pof0
except ImportError:
    from pac_inspect import FormatError, inspect_pac
    from yobj_read import read_yobj
    from texture_convert import read_gim8
    from yobj_alignment import align_yobj_pof0


def texture_table(names, payloads):
    if len(names) != len(payloads):
        raise FormatError('Texture name and payload counts differ')
    table = bytearray(struct.pack('<4I', len(names), 0x100, 0, 16))
    offset = 16 + 32 * len(names)
    for name, data in zip(names, payloads):
        encoded = name.encode('ascii')
        if len(encoded) > 15 or b'\0' in encoded:
            raise FormatError('Texture name cannot fit the PAC entry')
        read_gim8(data)
        table += encoded.ljust(16, b'\0') + b'gim\0' + struct.pack('<3I', len(data), offset, 0)
        offset += len(data)
    return bytes(table) + b''.join(payloads)


def replace_sections(base, replacements):
    report = inspect_pac(base)
    ids = [s['id'] for s in report['sections']]
    if len(set(ids)) != len(ids) or not set(replacements).issubset(ids):
        raise FormatError('Ambiguous or missing replacement section IDs')
    table = bytearray(b'PAC ' + struct.pack('<I', len(ids)))
    table_end = 8 + 8 * len(ids)
    payloads, offset = [], 0
    for section in report['sections']:
        # Align actual file addresses, including when the table is not 16-aligned.
        padding = (-(table_end + offset)) % 16
        payloads.append(bytes(padding))
        offset += padding
        payload = replacements.get(section['id'], base[section['offset']:section['offset'] + section['size']])
        if not payload or len(payload) >= 1 << 24 or offset >= 1 << 24:
            raise FormatError('PAC payload exceeds 24-bit table bounds')
        table += struct.pack('<H', section['id']) + offset.to_bytes(3, 'little') + len(payload).to_bytes(3, 'little')
        payloads.append(payload)
        offset += len(payload)
    result = bytes(table) + b''.join(payloads)
    result += bytes((-len(result)) % 2048)
    inspect_pac(result)
    return result


def repack(base_path, yobj_path, textures_path, output):
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    base, yobj = base_path.read_bytes(), yobj_path.read_bytes()
    try:
        yobj = align_yobj_pof0(yobj)
    except ValueError as exc:
        raise FormatError(str(exc)) from exc
    original = inspect_pac(base)
    models = [s for s in original['sections'] if s['id'] == 2 and s['kind'] == 'model_section']
    if len(models) != 1 or 9 not in [s['id'] for s in original['sections']]:
        raise FormatError('Not the supported PSP base PAC layout')
    section = models[0]
    base_model = read_yobj(base[section['offset']:section['offset'] + section['size']])
    model = read_yobj(yobj, psp_geometry=True)
    if model['bones'] != base_model['bones'] or model['warnings']:
        raise FormatError('Replacement skeleton or weights need investigation')
    manifest = json.loads((textures_path / 'textures.json').read_text())
    entries = sorted(manifest['textures'], key=lambda t: t['index'])
    if [t['name'] for t in entries] != model['textures']:
        raise FormatError('Model and texture table ordering differ')
    payloads = []
    for entry in entries:
        relative = Path(entry['gim'])
        if relative.is_absolute() or relative.name != entry['gim']:
            raise FormatError('Texture manifest path must be a filename')
        payloads.append((textures_path / relative).read_bytes())
    replacement = texture_table(model['textures'], payloads)
    result = replace_sections(base, {2: yobj, 9: replacement})
    after = inspect_pac(result)
    if any(s['offset'] % 16 for s in after['sections']):
        raise FormatError('PAC section alignment failed')
    before_by_id = {s['id']: s for s in original['sections']}
    for s in after['sections']:
        if s['id'] not in (2, 9) and s['sha256'] != before_by_id[s['id']]['sha256']:
            raise FormatError('Unrelated base section changed')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(result)
    return {'output_bytes': len(result), 'sha256': after['sha256'],
            'mesh_count': model['mesh_count'], 'bone_count': model['bone_count'],
            'triangles': model['triangle_count'], 'textures': len(payloads),
            'unchanged_sections': [s['id'] for s in after['sections'] if s['id'] not in (2, 9)],
            'section_alignment_bytes': 16,
            'relocation_chunk_aligned': len(yobj) % 16 == 0,
            'status': 'Experimental candidate; requires PPSSPP validation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--yobj', type=Path, required=True)
    parser.add_argument('--textures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(repack(args.base, args.yobj, args.textures, args.output), indent=2))
    except (OSError, FormatError) as exc:
        print(f'Repack failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
