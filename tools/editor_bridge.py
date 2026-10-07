"""Use the supplied editor's inspected serialization functions without its GUI.

Requires CPython 3.13 and the exact user-supplied editor version pinned below.
The executable's top-level code and GUI are never run. Its selected functions
are executed locally; the executable and its code are not redistributed.
"""
import argparse
import copy
import hashlib
import json
import marshal
import math
import os
from pathlib import Path
import struct
import sys
import types
import xml.etree.ElementTree as ET
import zlib

try:
    from .yobj_alignment import align_yobj_pof0
    from .psp_materials import regular_template
except ImportError:
    from yobj_alignment import align_yobj_pof0
    from psp_materials import regular_template


EDITOR_SHA256 = '1e6fe5db14eae75ebfa853c0a1ec74b1895531db75b037fa63728cbf6ae6129f'
READERS = ('read_header', 'read_mesh_header', 'read_mesh_header_bones', 'read_mesh_data_header',
           'read_flag', 'read_mesh_data', 'read_mesh_material', 'read_mesh_faces_header',
           'read_mesh_faces', 'read_bones', 'read_texture', 'read_model_name')
WRITERS = ('make_new_file', 'padding', 'write_header', 'write_mesh_header', 'write_mesh_header_bones',
           'write_mesh_data_header', 'write_mesh_data', 'write_mesh_material', 'write_mesh_faces_header',
           'write_mesh_faces', 'write_bones', 'write_texture', 'write_model_name', 'out',
           'generate_pof0', 'cleanup_duplicate_textures', 'write_file', 'export_as_one_dae')


def load_core(executable):
    if sys.version_info[:2] != (3, 13):
        raise ValueError('The supplied editor bytecode requires CPython 3.13')
    data = executable.read_bytes()
    if hashlib.sha256(data).hexdigest() != EDITOR_SHA256:
        raise ValueError('Unsupported editor version; do not execute uninspected bytecode')
    cookie = data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
    _, size, table, table_size, version, _ = struct.unpack_from('!8sIIII64s', data, cookie)
    if version != 313:
        raise ValueError('Unexpected editor Python version')
    start = len(data) - size
    position, end = start + table, start + table + table_size
    code = None
    while position < end:
        entry_size, offset, packed, unpacked, compressed, kind = struct.unpack_from('!IIIIBc', data, position)
        name = data[position + 18:position + entry_size].split(b'\0')[0]
        position += entry_size
        if name == b'yobj_mesh_editor_PSP_GUI' and kind == b's':
            payload = data[start + offset:start + offset + packed]
            payload = zlib.decompress(payload) if compressed else payload
            if len(payload) != unpacked:
                raise ValueError('Editor archive entry size mismatch')
            code = marshal.loads(payload)
    if code is None:
        raise ValueError('Missing editor module')
    env = {'__builtins__': __builtins__, 'struct': struct, 'math': math, 'copy': copy,
           'os': os, 'ET': ET, 'FILE_HEADER': b'YOBJ', 'all_offset': []}
    functions = {c.co_name: c for c in code.co_consts if isinstance(c, types.CodeType)}
    reset = functions['reset_variables']
    for name in reset.co_names:
        if name.startswith(('mesh_', 'new_', 'bone_', 'texture')) or name in ('bone', 'header', 'model_name', 'all_offset'):
            env[name] = []
    env['FILE_HEADER'] = b'YOBJ'
    for name in READERS + WRITERS:
        env[name] = types.FunctionType(functions[name], env)
    return env


def read_base(env, path):
    with path.open('rb') as stream:
        env['read_header'](stream)
        env['read_mesh_header'](stream)
        for i in range(env['mesh_count']):
            for name in READERS[2:9]:
                if name == 'read_flag':
                    env[name](i)
                else:
                    env[name](stream, i)
        for name in READERS[9:]:
            env[name](stream)


def configure_meshes(env, prepared):
    headers, materials, face_headers = copy.deepcopy((env['mesh_header'], env['mesh_material'], env['mesh_faces_header']))
    texture_bits = prepared['texture_bits']
    if len(texture_bits) != len(prepared['textures']):
        raise ValueError('Every prepared texture needs its native GIM color depth')
    fields = ('mesh_header', 'mesh_bones_count', 'mesh_bones', 'mesh_flag', 'mesh_flag_boolean',
              'mesh_flag_decode', 'mesh_data_lenght', 'mesh_data_count', 'mesh_data', 'mesh_bones_weight',
              'mesh_uv_u', 'mesh_uv_v', 'mesh_vertex_color', 'mesh_normal_x', 'mesh_normal_y', 'mesh_normal_z',
              'mesh_vertex_x', 'mesh_vertex_y', 'mesh_vertex_z', 'mesh_material_count', 'mesh_material',
              'mesh_material_texture', 'mesh_material_faces_count', 'mesh_faces_header', 'mesh_face_count', 'mesh_face')
    for name in fields:
        env[name] = []
    for mesh in prepared['meshes']:
        part = mesh['target_part']
        palette = mesh['bone_palette']
        vertices = mesh['vertices']
        count = len(palette)
        env['mesh_header'].append(headers[part])
        env['mesh_bones_count'].append(count)
        env['mesh_bones'].append(list(palette))  # DAE exporter expects array indices.
        env['mesh_flag'].append(0x17ff | ((count - 1) << 14))
        env['mesh_flag_boolean'].append(True)
        env['mesh_flag_decode'].append(count - 1)
        env['mesh_data_lenght'].append(36 + 4 * count)
        env['mesh_data_count'].append(len(vertices))
        env['mesh_bones_weight'].append([v['weights'] for v in vertices])
        env['mesh_uv_u'].append([v['uv'][0] for v in vertices])
        # Prepared JSON uses Blender UVs. Native YOBJ uses top-origin V.
        native_v = [1 - v['uv'][1] if prepared['uv_v_flipped'] else v['uv'][1] for v in vertices]
        env['mesh_uv_v'].append(native_v)
        env['mesh_vertex_color'].append([v['color'] for v in vertices])
        for axis, letter in enumerate('xyz'):
            env['mesh_vertex_' + letter].append([v['position'][axis] for v in vertices])
            env['mesh_normal_' + letter].append([v['normal'][axis] for v in vertices])
        records = []
        for vertex, v in zip(vertices, native_v):
            records.append(struct.pack('<' + 'f' * count, *vertex['weights'])
                           + struct.pack('<2f4B6f', vertex['uv'][0], v, *vertex['color'],
                                         *vertex['normal'], *vertex['position']))
        env['mesh_data'].append(records)
        mats = mesh['materials']
        env['mesh_material_count'].append(len(mats))
        env['mesh_material'].append([
            regular_template(materials, part, texture_bits[m['texture_id']]) for m in mats])
        env['mesh_material_texture'].append([m['texture_id'] for m in mats])
        env['mesh_material_faces_count'].append([len(m['strips']) for m in mats])
        env['mesh_faces_header'].append([[face_headers[part][0][0] for _ in m['strips']] for m in mats])
        env['mesh_face_count'].append([[len(s) for s in m['strips']] for m in mats])
        env['mesh_face'].append([m['strips'] for m in mats])
    env['mesh_count'] = len(prepared['meshes'])
    env['texture'] = prepared['textures']
    env['texture_count'] = len(prepared['textures'])
    for name in ('mesh_bones_header_offset', 'mesh_data_header_offset', 'mesh_data_start_offset', 'mesh_material_header_offset'):
        env[name] = [8] * env['mesh_count']
    for name in ('mesh_material_faces_header_offset', 'mesh_material_faces_start_offset'):
        env[name] = [[8] * len(m['materials']) for m in prepared['meshes']]
    env['mesh_face_offset'] = [[[8] * len(mat['strips']) for mat in m['materials']] for m in prepared['meshes']]


def export(executable, base, prepared_path, output):
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    prepared = json.loads(prepared_path.read_text())
    env = load_core(executable)
    read_base(env, base)
    if env['bone_name'] != [b['name'] for b in prepared['bones']]:
        raise ValueError('Prepared skeleton differs from the supplied PSP base')
    configure_meshes(env, prepared)
    output.mkdir(parents=True, exist_ok=False)
    env['export_as_one_dae'](str(output / 'prepared.dae'))
    # The inspected editor's writer also copies bone_count from header rather
    # than deriving it from geometry. The original base bone records stay intact.
    env['mesh_bones'] = [[b + 1 for b in palette] for palette in env['mesh_bones']]
    with (output / 'prepared.yobj').open('w+b') as target:
        env['make_new_file'](target)
        env['write_header'](target)
        env['write_mesh_header'](target)
        for i in range(env['mesh_count']):
            for name in ('write_mesh_header_bones', 'write_mesh_data_header', 'write_mesh_data',
                         'write_mesh_material', 'write_mesh_faces_header', 'write_mesh_faces'):
                env[name](target, i)
        for name in ('write_bones', 'write_texture', 'write_model_name', 'generate_pof0'):
            env[name](target)
        target.seek(0)
        aligned = align_yobj_pof0(target.read())
        target.seek(0)
        target.write(aligned)
        target.truncate()
    print('EDITOR_EXPORT_COMPLETED', output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor', type=Path, required=True)
    parser.add_argument('--base-yobj', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.editor, args.base_yobj, args.prepared, args.output)


if __name__ == '__main__':
    main()
