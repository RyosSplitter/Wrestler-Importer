"""Read original skin weights from the observed HCTP PS2 VIF layout.

Analysis reader only; the pinned beta backend is not changed. Position/normal
buffers use 160-slot VU regions, and weights begin at VU address 0x280 even
when the mesh contains fewer than 160 vertices. Groups with one bone have an
implicit weight of 1. Blended groups use V4-32 UNPACK packets indexed by their
VU destination. Unsupported packet layouts are rejected rather than guessed.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

from .hctp_read import read_hctp
from .pac_inspect import FormatError, inspect_pac, select_model_section
from .yobj_read import Reader


def decode_weight_packets(data, start, qwords, vertex_count, groups):
    if not 0 < vertex_count <= 160 or qwords < 0:
        raise FormatError('Unsupported HCTP VU vertex allocation')
    reader = Reader(data)
    reader.check(start, qwords * 16)
    end = start + qwords * 16
    records, packets = {}, []
    cursor = start
    while cursor < end:
        zeros = reader.unpack('<3I', cursor)
        command = reader.u32(cursor + 12)
        if zeros != (0, 0, 0) or command >> 24 != 0x6C or command & 0xFC00:
            raise FormatError('Unsupported HCTP weight VIF command')
        count = (command >> 16) & 255 or 256
        first = (command & 0x3FF) - 0x280
        if first < 0 or first + count > vertex_count:
            raise FormatError('HCTP weight VU destination outside mesh')
        cursor += 16
        if cursor + count * 16 > end:
            raise FormatError('Truncated HCTP weight UNPACK payload')
        packets.append({'destination': command & 0x3FF, 'first_vertex': first,
                        'vertex_count': count, 'file_offset': cursor - 16})
        for i in range(count):
            index = first + i
            if index in records:
                raise FormatError('Overlapping HCTP weight packets')
            records[index] = reader.unpack('<4f', cursor + i * 16)
        cursor += count * 16
    if cursor != end:
        raise FormatError('HCTP weight packet length mismatch')

    weights = [None] * vertex_count
    errors = []
    expected_explicit = set()
    for group in groups:
        bones = group['source_bones']
        if not 1 <= len(bones) <= 4 or len(set(bones)) != len(bones):
            raise FormatError('Unsupported HCTP skin group palette')
        first, count = group['source_vertex_start'], group['vertex_count']
        if first < 0 or count <= 0 or first + count > vertex_count:
            raise FormatError('HCTP skin group outside mesh')
        for index in range(first, first + count):
            if weights[index] is not None:
                raise FormatError('Overlapping HCTP skin groups')
            if len(bones) == 1:
                if index in records:
                    raise FormatError('Unexpected explicit weight for rigid HCTP group')
                values = (1.0,)
            else:
                expected_explicit.add(index)
                if index not in records:
                    raise FormatError('Missing blended HCTP vertex weights')
                raw = records[index]
                if any(not math.isfinite(w) or w < 0 or w > 1 for w in raw):
                    raise FormatError('Invalid HCTP weight value')
                if any(w != 0 for w in raw[len(bones):]):
                    raise FormatError('Nonzero unused HCTP weight slot')
                values = raw[:len(bones)]
            error = abs(sum(values) - 1)
            if error > 1e-5:
                raise FormatError('HCTP skin weights are not normalized')
            errors.append(error)
            weights[index] = list(zip(bones, values))
    if any(w is None for w in weights) or set(records) != expected_explicit:
        raise FormatError('Incomplete HCTP skin group/packet coverage')
    return weights, {'packets': packets, 'explicit_vertices': len(records),
                     'implicit_rigid_vertices': vertex_count - len(records),
                     'weight_sum_max_error': max(errors, default=0)}


def read_hctp_with_weights(data):
    model = read_hctp(data)
    reader = Reader(data)
    reader.limit = model['declared_end']
    reports = []
    for mesh in model['meshes']:
        address = reader.u32(36) + 8 + mesh['index'] * 64
        start, qwords = reader.u32(address + 28) + 8, reader.u32(address + 36)
        reader.check(start, qwords * 16)
        weights, report = decode_weight_packets(data, start, qwords,
                                               mesh['source_vertex_count'], mesh['source_groups'])
        palette = sorted({bone for group in mesh['source_groups'] for bone in group['source_bones']})
        mesh['bone_palette'] = palette
        for vertex in mesh['vertices']:
            source = weights[vertex['source_vertex_index']]
            dense = dict(source)
            vertex['weights'] = [dense.get(b, 0.0) for b in palette]
            vertex['original_source_influences'] = copy.deepcopy(source)
        reports.append({'mesh': mesh['index'], **report})
    model['source_skinning_decoded'] = True
    model['source_weight_report'] = {
        'layout': 'Observed HCTP VIF V4-32 at fixed VU weight base 0x280; rigid groups implicit',
        'meshes': reports,
        'exact_values_retained': True,
        'limitations': ['Packet/palette interpretation validated structurally on supplied HCTP files; '
                        'source animation playback is not an independent decoder validation']}
    return model


def load_hctp_with_weights(path: Path):
    data = path.read_bytes()
    if data.startswith(b'PAC '):
        pac = inspect_pac(data)
        section = select_model_section(pac)
        data = data[section['offset']:section['offset'] + section['size']]
    return read_hctp_with_weights(data)
