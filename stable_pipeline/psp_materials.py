"""Material templates observed in the supplied SVR 2007 PSP Kurt base.

The full control word is not decoded. Regular 4-bit materials use 0x5,
regular 8-bit materials use 0x7, and blood-overlay materials use 0x115
in that sample. Reuse a matching complete regular record, not overlay state.
"""
import struct


REGULAR_CONTROLS = {4: 0x5, 8: 0x7}


def material_control(record):
    if len(record) != 144:
        raise ValueError('Expected a 144-byte PSP material record')
    return struct.unpack_from('<I', record, 24)[0]


def regular_template(materials, part, bits):
    if bits not in REGULAR_CONTROLS:
        raise ValueError('Only the observed indexed4/indexed8 material profile is supported')
    wanted = REGULAR_CONTROLS[bits]
    # Prefer the destination body part, then another regular base material.
    # Some nearest parts contain only blood-effect geometry.
    for candidates in (materials[part], [m for group in materials for m in group]):
        for record in candidates:
            if material_control(record) == wanted:
                return bytes(record)
    raise ValueError(f'PSP base has no regular {bits}-bit material template')


def validate_material_controls(model, texture_bits):
    if len(texture_bits) != len(model['textures']):
        raise ValueError('Material validation requires every native texture color depth')
    for mesh in model['meshes']:
        for material in mesh['materials']:
            tid = material['texture_id']
            bits = texture_bits[tid]
            control = material['control']
            name = model['textures'][tid]
            # Preserve the observed effect convention for unchanged base models.
            if control == 0x115 and name.lower() in ('blood', 'blood_b') and bits == 4:
                continue
            if bits not in REGULAR_CONTROLS or control != REGULAR_CONTROLS[bits]:
                raise ValueError(f'Texture {name}: material control 0x{control:x} does not match the regular {bits}-bit PSP profile')
