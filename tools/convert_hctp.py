"""One-command experimental HCTP -> SVR 2007 PSP conversion.

The output is a candidate for PPSSPP testing, not a claim of game compatibility.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

try:
    from .hctp_read import load_hctp
    from .pac_inspect import FormatError, inspect_pac
    from .pac_repack import repack
    from .prepare_model import prepare
    from .texture_convert import convert_pac, write_preview_textures
    from .yobj_read import load_model
except ImportError:
    from hctp_read import load_hctp
    from pac_inspect import FormatError, inspect_pac
    from pac_repack import repack
    from prepare_model import prepare
    from texture_convert import convert_pac, write_preview_textures
    from yobj_read import load_model


def _canonical(triangle):
    a, b, c = triangle
    return min((a, b, c), (b, c, a), (c, a, b))


def verify_serialized(prepared, base_bytes, yobj_path):
    actual_bytes = yobj_path.read_bytes()
    def bone_table(data):
        count = struct.unpack_from('<I', data, 28)[0]
        start = struct.unpack_from('<I', data, 40)[0] + 8
        return data[start:start + 80 * count]
    if bone_table(base_bytes) != bone_table(actual_bytes):
        raise FormatError('Original PSP bone table bytes changed')
    actual = load_model(yobj_path, psp_geometry=True)
    if actual['warnings'] or actual['mesh_count'] != prepared['mesh_count']:
        raise FormatError('Serialized YOBJ structure needs investigation')
    def close(a, b):
        return len(a) == len(b) and all(math.isclose(x, y, abs_tol=1e-6, rel_tol=1e-6) for x, y in zip(a, b))
    for expected, observed in zip(prepared['meshes'], actual['meshes']):
        if expected['bone_palette'] != list(observed['bone_palette']) or len(expected['vertices']) != len(observed['vertices']):
            raise FormatError('Serialized palette/vertex count changed')
        for v, w in zip(expected['vertices'], observed['vertices']):
            uv = [v['uv'][0], 1 - v['uv'][1] if prepared['uv_v_flipped'] else v['uv'][1]]
            matches = (close(v['position'], w['position']), close(v['normal'], w['normal']),
                       close(v['weights'], w['weights']), close(uv, w['uv']), list(v['color']) == list(w['color']))
            if not all(matches):
                raise FormatError('Serialized vertex attributes changed')
        if len(expected['materials']) != len(observed['materials']):
            raise FormatError('Serialized material count changed')
        for a, b in zip(expected['materials'], observed['materials']):
            if a['texture_id'] != b['texture_id'] or Counter(map(_canonical, a['triangles'])) != Counter(map(_canonical, b['triangles'])):
                raise FormatError('Serialized material/triangle winding changed')
    return {'bone_table_byte_identical': True, 'vertex_attributes_match': True,
            'triangles_and_winding_match': True, 'native_yobj_warnings': actual['warnings']}


def convert(source, target, reference, editor, output, editor_python):
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    editor_python = str(editor_python)
    check = subprocess.run([editor_python, '-c', 'import sys; sys.exit(0 if sys.version_info[:2]==(3,13) else 1)'], check=False)
    if check.returncode:
        raise FormatError('Editor serialization requires CPython 3.13; select it with --editor-python')
    model, preparation = prepare(load_hctp(source), load_model(target, psp_geometry=True),
                                 load_model(reference, psp_geometry=True))
    output.mkdir(parents=True, exist_ok=False)
    (output / 'prepared.json').write_text(json.dumps(model, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    texture_manifest = convert_pac(source, output / 'textures')
    base = target.read_bytes()
    sections = [s for s in inspect_pac(base)['sections'] if s['id'] == 2 and s['kind'] == 'model_section']
    if len(sections) != 1:
        raise FormatError('Expected one model section in PSP base')
    section = sections[0]
    base_yobj = base[section['offset']:section['offset'] + section['size']]
    (output / 'base-model.bin').write_bytes(base_yobj)
    with (output / 'editor.log').open('w', encoding='utf-8') as log:
        subprocess.run([editor_python, str(Path(__file__).with_name('editor_bridge.py')),
                        '--editor', str(editor.resolve()), '--base-yobj', str((output / 'base-model.bin').resolve()),
                        '--prepared', str((output / 'prepared.json').resolve()), '--output', str((output / 'native').resolve())],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    verification = verify_serialized(model, base_yobj, output / 'native' / 'prepared.yobj')
    preview_files = write_preview_textures(texture_manifest, output / 'textures', output / 'native')
    pac = output / 'RVD-HCTP-to-SVR2007-PSP-test.pac'
    packing = repack(target, output / 'native' / 'prepared.yobj', output / 'textures', pac)
    report = {'preparation': preparation, 'textures': texture_manifest, 'native_serialization': verification,
              'preview_texture_files': preview_files,
              'pac': packing, 'status': 'Experimental test candidate; PPSSPP validation is pending'}
    (output / 'conversion-report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('reference', type=Path)
    parser.add_argument('--editor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--editor-python', default=sys.executable)
    args = parser.parse_args()
    try:
        report = convert(args.source, args.target, args.reference, args.editor, args.output, args.editor_python)
        print(json.dumps({'output': str(args.output), **report['pac']}, indent=2))
    except (OSError, FormatError, subprocess.CalledProcessError) as exc:
        print(f'Conversion failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
