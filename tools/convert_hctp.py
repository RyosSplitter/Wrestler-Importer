"""One-command experimental HCTP -> SVR 2007 PSP conversion.

The output is a candidate for PPSSPP testing, not a claim of game compatibility.
"""
import argparse
from collections import Counter
import json
import math
import os
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
    from .psp_materials import REGULAR_CONTROLS
    from .region_mesh import pack_regions
except ImportError:
    from hctp_read import load_hctp
    from pac_inspect import FormatError, inspect_pac
    from pac_repack import repack
    from prepare_model import prepare
    from texture_convert import convert_pac, write_preview_textures
    from yobj_read import load_model
    from psp_materials import REGULAR_CONTROLS
    from region_mesh import pack_regions


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
        flag_base = {'float': 0x17ff, 'psp_u8': 0x13ff, 'psp_u16': 0x15ff}[prepared.get('weight_encoding', 'float')]
        if observed['flag'] != flag_base | ((len(expected['bone_palette'])-1)<<14):
            raise FormatError('Serialized PSP vertex format changed')
        if expected['bone_palette'] != list(observed['bone_palette']) or len(expected['vertices']) != len(observed['vertices']):
            raise FormatError('Serialized palette/vertex count changed')
        for v, w in zip(expected['vertices'], observed['vertices']):
            if prepared['preparation_report']['vertex_alpha']['policy'] == 'opaque_psp_base' and w['color'][3] != 255:
                raise FormatError('PSP base opacity policy was lost during serialization')
            uv = [v['uv'][0], 1 - v['uv'][1] if prepared['uv_v_flipped'] else v['uv'][1]]
            matches = (close(v['position'], w['position']), close(v['normal'], w['normal']),
                       close(v['weights'], w['weights']), close(uv, w['uv']), list(v['color']) == list(w['color']))
            if not all(matches):
                raise FormatError('Serialized vertex attributes changed')
            if prepared.get('regional') and not math.isclose(math.sqrt(sum(n*n for n in w['normal'])), 1., abs_tol=1e-5):
                raise FormatError('Decimated PSP normal is not normalized')
        if len(expected['materials']) != len(observed['materials']):
            raise FormatError('Serialized material count changed')
        for a, b in zip(expected['materials'], observed['materials']):
            if a['texture_id'] != b['texture_id'] or Counter(map(_canonical, a['triangles'])) != Counter(map(_canonical, b['triangles'])):
                raise FormatError('Serialized material/triangle winding changed')
            bits = prepared['texture_bits'][a['texture_id']]
            if b['control'] != REGULAR_CONTROLS[bits]:
                raise FormatError('Ordinary source texture has incompatible PSP material state')
    return {'bone_table_byte_identical': True, 'vertex_attributes_match': True,
            'vertex_weight_encoding': prepared.get('weight_encoding', 'float'),
            'triangles_and_winding_match': True, 'regular_material_controls_match_texture_depth': True,
            'vertex_alpha_matches_preparation_policy': True,
            'native_yobj_warnings': actual['warnings']}


def convert(source, target, reference, editor, output, editor_python, *, compact=False, blender='blender', detail=False, regional=False):
    if regional:
        compact = detail = True
    if detail and not compact:
        raise FormatError('The facial detail profile requires --compact')
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    editor_python = str(editor_python)
    check = subprocess.run([editor_python, '-c', 'import sys; sys.exit(0 if sys.version_info[:2]==(3,13) else 1)'], check=False)
    if check.returncode:
        raise FormatError('Editor serialization requires CPython 3.13; select it with --editor-python')
    source_model = load_hctp(source)
    target_model, donor_model = load_model(target, psp_geometry=True), load_model(reference, psp_geometry=True)
    output.mkdir(parents=True, exist_ok=False)
    if regional:
        source_model, _ = prepare(source_model, target_model, donor_model)
    if compact:
        source_file, reduced_file = output / 'source.json', output / 'reduced-source.json'
        source_file.write_text(json.dumps(source_model, allow_nan=False), encoding='utf-8')
        env = os.environ.copy()
        for name, folder in [('BLENDER_USER_CONFIG', 'blender-config'), ('BLENDER_USER_EXTENSIONS', 'blender-extensions'), ('MESA_SHADER_CACHE_DIR', 'mesa-cache')]:
            env.setdefault(name, str((output / folder).resolve()))
        with (output / 'reduction.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(blender), '--background', '--python-exit-code', '1', '--python',
                            str(Path(__file__).with_name('blender_reduce.py').resolve()), '--',
                            str(source_file.resolve()), str(reduced_file.resolve()),
                            '0.20' if detail else '0.3', *(['--detail-profile'] if detail else []),
                            *(['--regions'] if regional else [])],
                           stdout=log, stderr=subprocess.STDOUT, env=env, check=True)
        source_model = json.loads(reduced_file.read_text())
    if regional:
        model = pack_regions(source_model)
        preparation = model['preparation_report']
    else:
        model, preparation = prepare(source_model, target_model, donor_model, max_influences=2 if detail else 4)
    texture_budgets = {'bn_kao2': (128, 8)} if detail else {}
    if regional:
        texture_budgets['bn_dou'] = (64, 8)
    texture_manifest = convert_pac(source, output / 'textures', max_dimension=64 if compact else None, bits=4 if compact else 8,
                                   texture_budgets=texture_budgets,
                                   preserve_cutout_alpha=regional)
    model['texture_bits'] = [t['bits'] for t in sorted(texture_manifest['textures'], key=lambda t: t['index'])]
    (output / 'prepared.json').write_text(json.dumps(model, indent=2, allow_nan=False) + '\n', encoding='utf-8')
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
    float_verification = None
    if regional:
        with (output / 'editor-float-preview.log').open('w', encoding='utf-8') as log:
            subprocess.run([editor_python, str(Path(__file__).with_name('editor_bridge.py')),
                            '--editor', str(editor.resolve()), '--base-yobj', str((output / 'base-model.bin').resolve()),
                            '--prepared', str((output / 'prepared.json').resolve()), '--output', str((output / 'native-float').resolve()),
                            '--float-preview'], stdout=log, stderr=subprocess.STDOUT, check=True)
        float_verification = verify_serialized({**model, 'weight_encoding': 'float'}, base_yobj, output / 'native-float' / 'prepared.yobj')
        write_preview_textures(texture_manifest, output / 'textures', output / 'native-float')
    pac = output / ('RVD-HCTP-to-PSP-region-test.pac' if regional else
                    'RVD-HCTP-to-SVR2007-PSP-compact-test.pac' if compact else 'RVD-HCTP-to-SVR2007-PSP-test.pac')
    packing = repack(target, output / 'native' / 'prepared.yobj', output / 'textures', pac,
                     max_bytes=148 * 1024 if compact else None)
    report = {'preparation': preparation, 'textures': texture_manifest, 'native_serialization': verification,
              'preview_texture_files': preview_files,
              'float_preview_serialization': float_verification,
              'reduction': source_model.get('reduction_report'), 'compact': compact, 'detail': detail, 'regional': regional,
              'pac_filename': pac.name,
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
    parser.add_argument('--compact', action='store_true', help='Blender reduction, 4-bit/64px textures, maximum 148 KiB PAC')
    parser.add_argument('--blender', default='blender', help='Blender 4.3 executable for compact conversion')
    parser.add_argument('--detail', action='store_true', help='Preserve eyes/teeth/mouth and allocate more detail to the face')
    parser.add_argument('--regions', action='store_true', help='PSP-weight region reduction: head 80%, torso 50%, limbs 35%, 148 KiB maximum')
    args = parser.parse_args()
    try:
        report = convert(args.source, args.target, args.reference, args.editor, args.output, args.editor_python,
                         compact=args.compact, blender=args.blender, detail=args.detail, regional=args.regions)
        print(json.dumps({'output': str(args.output), **report['pac']}, indent=2))
    except (OSError, FormatError, subprocess.CalledProcessError) as exc:
        print(f'Conversion failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
