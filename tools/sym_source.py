"""Read-only research readers for the supplied SYM CH.PAC variant.

These are not registered source adapters. Unknown layouts fail explicitly;
original records, inter-entry trailers and fourth channels are never repaired.
"""
from __future__ import annotations

import hashlib
import struct

import numpy as np

from tools.pac_inspect import FormatError, inspect_pac
from tools.sym_research import tim2_headers


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_ch_directory(data):
    """Strict single EMD directory, observed 256-byte lengths/2048 alignment.

    Header word +12 and four-byte allocation trailers have unknown semantics.
    Report them without treating them as offsets, checksums or disposable zeros.
    """
    if not 0x4000 <= len(data) <= 64 * 1024 * 1024 or data[:4] != b'DPAC':
        raise FormatError('Not the bounded SYM single-group DPAC variant')
    table_bytes, payload_bytes, unknown = struct.unpack_from('<3I', data, 4)
    if any(data[16:0x800]) or data[0x800:0x804] != b'EMD ':
        raise FormatError('Unsupported DPAC header/directory variant')
    flagged_count, reserved = struct.unpack_from('<HH', data, 0x804)
    count = flagged_count & 0x7fff
    if not flagged_count & 0x8000 or not 0 < count <= 4096 or reserved:
        raise FormatError('Unsupported DPAC group flags/count/reserved field')
    if table_bytes != 8 + count * 4:
        raise FormatError('DPAC directory byte count mismatch')
    start = len(data) - payload_bytes
    if start < 0x800 + table_bytes or start % 2048 or start > len(data):
        raise FormatError('DPAC payload range/alignment mismatch')
    if any(data[0x800 + table_bytes:start]):
        raise FormatError('Nonzero directory gap: unsupported DPAC variant')
    entries = []
    seen = set()
    cursor = start
    for i in range(count):
        ident, units = struct.unpack_from('<HH', data, 0x808 + 4*i)
        size = units * 256
        end = cursor + size
        next_offset = (end + 2047) // 2048 * 2048
        if ident in seen or not units or next_offset > len(data):
            raise FormatError('Duplicate ID, empty entry or DPAC entry outside allocation')
        raw = data[cursor:end]
        inspect_pac(raw)  # Directory arithmetic alone is insufficient.
        gap = data[end:next_offset]
        entries.append(dict(index=i, id=ident, id_hex=f'{ident:04x}', offset=cursor,
            stored_bytes=size, size_units_256=units, sha256=sha(raw),
            allocation_end=next_offset, gap_bytes=len(gap), gap_sha256=sha(gap),
            gap_nonzero_bytes=sum(x != 0 for x in gap),
            gap_prefix_zero=not any(gap[:-4]),
            allocation_trailer_hex=gap[-4:].hex() if len(gap) >= 4 else None))
        seen.add(ident)
        cursor = next_offset
    if cursor != len(data):
        raise FormatError('DPAC cumulative allocations do not consume payload exactly')
    return dict(schema='ps2psp.sym-ch-directory/1', bytes=len(data), sha256=sha(data),
        table_offset=0x800, table_bytes=table_bytes, payload_offset=start,
        payload_bytes=payload_bytes, unknown_header_word_12=unknown,
        group_flags=flagged_count & 0x8000, entry_count=count, entries=entries,
        conversion_supported=False)


def read_atlas(data):
    """Observed TIM2 v4 format-0: one linear PSMT8/4 image, RGBA32 CSM1 CLUT.

    Low nibble first for indexed4; indexed8 CLUT bits 3/4 are exchanged.
    PS2 alpha 0..128 is mapped to 0..255 for preview. Raw palette is retained.
    This does not establish runtime blending semantics for every SYM material.
    """
    header = tim2_headers(data)
    if header['version'] != 4 or header['picture_count'] != 1 or header['trailing_bytes']:
        raise FormatError('Unsupported TIM2 version/count/trailing bytes')
    p = header['pictures'][0]
    bits = {4: 4, 5: 8}.get(p['image_type'])
    if (bits is None or p['clut_type'] != 3 or p['picture_format'] != 0
            or p['mipmap_count'] != 1 or p['header_bytes'] != 48):
        raise FormatError('Unsupported SYM TIM2 pixel/CLUT/header/mipmap variant')
    width, height = p['width'], p['height']
    tex0 = int.from_bytes(bytes.fromhex(p['gs_tex0_hex']), 'little')
    registers = dict(psm=(tex0 >> 20) & 63, tw=(tex0 >> 26) & 15,
        th=(tex0 >> 30) & 15, cpsm=(tex0 >> 51) & 15,
        csm=(tex0 >> 55) & 1, csa=(tex0 >> 56) & 31)
    if (registers['psm'] != {4: 20, 8: 19}[bits]
            or 1 << registers['tw'] != width or 1 << registers['th'] != height
            or any(registers[k] for k in ('cpsm', 'csm', 'csa'))):
        raise FormatError('Unsupported/inconsistent TIM2 TEX0 registers')
    pixels = width * height
    colors = 1 << bits
    if not 0 < pixels <= 4 * 1024 * 1024 or pixels % 2:
        raise FormatError('Unsupported TIM2 dimensions/pixel allocation')
    if (p['image_bytes'] != pixels * bits // 8 or p['clut_bytes'] != colors * 4
            or p['declared_colors'] != colors
            or p['total_bytes'] != p['header_bytes'] + p['image_bytes'] + p['clut_bytes']):
        raise FormatError('TIM2 pixel/palette allocation mismatch')
    offset = p['offset'] + p['header_bytes']
    image = np.frombuffer(data, np.uint8, p['image_bytes'], offset)
    if bits == 4:
        indices = np.empty(pixels, dtype=np.uint8)
        indices[::2], indices[1::2] = image & 15, image >> 4
    else:
        indices = image.copy()
    raw_palette = np.frombuffer(data, np.uint8, colors*4, offset+p['image_bytes']).reshape(colors, 4).copy()
    perm = np.arange(colors)
    if bits == 8:
        perm = (perm & ~24) | ((perm & 8) << 1) | ((perm & 16) >> 1)
    palette = raw_palette[perm].copy()
    palette[:, 3] = np.minimum(palette[:, 3].astype(np.uint16)*255//128, 255)
    metadata = dict(p, gs_tex0=registers, bits_per_index=bits, palette_entries=colors,
        raw_palette_alpha_min=int(raw_palette[:, 3].min()),
        raw_palette_alpha_max=int(raw_palette[:, 3].max()),
        useful_rgba_colors=int(len(np.unique(palette[np.unique(indices)], axis=0))),
        pixel_layout='linear candidate; visual verification required',
        palette_layout='RGBA32 CSM1 candidate', alpha_forced_opaque=False,
        source_sha256=sha(data))
    return indices.reshape(height, width), palette, metadata
