"""Isolated native texture-depth experiments; no production registration.

Changing GIM depth requires matching native regular material control metadata.
Only that audited field is patched; all vertex/index/rig data stays byte-exact.
"""
import struct
import numpy as np
from desktop.texture_optimizer.candidates import read_gim, write_gim
from tools.psp_mesh_audit import audit_yobj, relocations


def exact_indexed4(raw):
    indices, palette = read_gim(raw); image = palette[indices]
    if np.any(image[:, :, 3] != 255):
        raise ValueError('Only opaque regular pages are eligible')
    colors, inverse = np.unique(image.reshape(-1, 4), axis=0, return_inverse=True)
    if len(colors) > 16:
        raise ValueError('More than 16 actual RGBA colors')
    clut = np.zeros((16, 4), np.uint8); clut[:len(colors)] = colors
    encoded = write_gim(inverse.reshape(indices.shape).astype(np.uint8), clut, 4)
    ix, pal = read_gim(encoded)
    if not np.array_equal(pal[ix], image):
        raise ValueError('Lossless palette conversion changed pixels')
    return encoded


def patch_regular_depths(raw, bits_by_name):
    before = audit_yobj(raw); names = before['texture_names']
    if set(bits_by_name) != set(names) or any(v not in (4, 8) for v in bits_by_name.values()):
        raise ValueError('Every texture needs an observed indexed4/indexed8 contract')
    output = bytearray(raw); changes = []
    for mesh in before['meshes']:
        allocation = next(a for a in before['report']['allocations'] if a['kind'] == f"mesh {mesh['index']} materials")
        for i, material in enumerate(mesh['materials']):
            name = names[material['texture_id']]; control = material['control']; wanted = bits_by_name[name]
            if control not in (5, 7, 0x115, 0x117):
                raise ValueError('Unreviewed material control')
            old_bits = 4 if control in (5, 0x115) else 8
            if wanted == old_bits: continue
            if control not in (5, 7):
                raise ValueError('Cutout/effect controls must remain unchanged')
            new_control = 5 if wanted == 4 else 7
            address = allocation['start'] + i * 144 + 24
            if struct.unpack_from('<I', raw, address)[0] != control:
                raise ValueError('Material allocation disagrees with audit')
            struct.pack_into('<I', output, address, new_control)
            changes.append(dict(mesh=mesh['index'], material=i, texture=name, offset=address,
                                before=control, after=new_control, old_bits=old_bits, new_bits=wanted))
    result = bytes(output); after = audit_yobj(result)
    if len(result) != len(raw) or before['bone_raw'] != after['bone_raw'] or relocations(raw) != relocations(result):
        raise ValueError('Unexpected rig/layout change')
    allowed = set(a for c in changes for a in range(c['offset'], c['offset'] + 4))
    if any(a not in allowed for a, (x, y) in enumerate(zip(raw, result)) if x != y):
        raise ValueError('Unreported native byte change')
    for a, b in zip(before['meshes'], after['meshes']):
        for field in ('raw_header', 'raw_palette_header', 'raw_vertices', 'bone_palette'):
            if a[field] != b[field]: raise ValueError('Vertex/palette metadata changed')
        for x, y in zip(a['materials'], b['materials']):
            if x['strips'] != y['strips'] or x['strip_headers'] != y['strip_headers']:
                raise ValueError('Index/strip data changed')
    return result, dict(material_control_changes=changes, all_other_native_bytes_exact=True,
                        geometry_vertex_index_uv_normal_weight_and_rig_bytes_exact=True,
                        policy='Only observed regular indexed4/indexed8 material-control words may differ')
