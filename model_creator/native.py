"""Creator-only descriptor-array reader. The converter auditor is unchanged.

Array counts partition the contiguous mesh table in the supplied native corpus.
This adapter validates the additional allocations independently before using the
existing auditor for GE buffers, weights, indices and relocation coverage.
"""
import struct

from tools.psp_mesh_audit import audit_yobj as ordinary_audit, encode_relocations
from tools.yobj_alignment import align_yobj_pof0


def audit_yobj(raw):
    if len(raw) < 72:
        raise ValueError('Truncated YOBJ header')
    count = struct.unpack_from('<I', raw, 52)[0] or 1
    start = 8 + struct.unpack_from('<I', raw, 48)[0]
    end = 8 + struct.unpack_from('<I', raw, 4)[0]
    meshes = struct.unpack_from('<I', raw, 24)[0]
    if not 1 <= count <= 16 or start < 72 or start % 4 or start + 32*count > end:
        raise ValueError('Invalid descriptor-array bounds')
    records = [raw[start+i*32:start+(i+1)*32] for i in range(count)]
    sizes = [struct.unpack_from('<I', r, 24)[0] for r in records]
    if sum(sizes) != meshes or any(n == 0 for n in sizes):
        raise ValueError('Descriptor counts do not partition the mesh table')
    if count > 1 and any(struct.unpack_from('<2I', r, 16) != (1, 0) or struct.unpack_from('<I', r, 28)[0] for r in records):
        raise ValueError('Unknown multi-descriptor semantics')
    adjusted = bytearray(raw)
    struct.pack_into('<I', adjusted, start+24, meshes)
    model = ordinary_audit(bytes(adjusted))
    for allocation in model['report']['allocations']:
        if allocation['start'] == start and allocation['kind'] == 'model name and descriptor':
            allocation.update(end=start+32*count, bytes=32*count, kind='model descriptor array')
        elif allocation['bytes'] and allocation['start'] < start+32*count and allocation['end'] > start:
            raise ValueError('Descriptor array overlaps another allocation')
    model.update(header=raw[:72], model_descriptor_raw=records[0], descriptors=records)
    owners=[]
    for i, n in enumerate(sizes): owners.extend([i]*n)
    model['descriptor_owners']=owners
    model['report'].update(descriptor_count=count, descriptor_mesh_counts=sizes,
        descriptor_array_independently_validated=True, model_descriptor_hex=records[0].hex())
    return model


def restore_descriptors(raw, records, sizes):
    """Replace the final single descriptor, retaining every other allocation."""
    model=ordinary_audit(raw)
    start=8+struct.unpack_from('<I',raw,48)[0]
    end=8+struct.unpack_from('<I',raw,4)[0]
    if start+32 != end or len(records)!=len(sizes) or sum(sizes)!=len(model['meshes']):
        raise ValueError('Descriptor restoration requires the verified final allocation')
    array=bytearray()
    for record,n in zip(records,sizes):
        if len(record)!=32 or n<1:raise ValueError('Invalid descriptor record')
        record=bytearray(record);struct.pack_into('<I',record,24,n);array.extend(record)
    payload=bytearray(raw[:start]+array)
    struct.pack_into('<I',payload,52,len(records))
    for offset in (4,12):struct.pack_into('<I',payload,offset,len(payload)-8)
    reloc=encode_relocations(model['report']['relocation_locations'])
    output=align_yobj_pof0(payload+b'POF0'+struct.pack('<I',len(reloc))+reloc)
    audit_yobj(output)
    return output


def allocation_fill(raw, model):
    targets={8+struct.unpack_from('<I',raw,a)[0] for a in model['report']['relocation_locations']}
    allocations=sorted(model['report']['allocations'],key=lambda a:a['start'])
    cursor=0;fills=[]
    for allocation in allocations:
        start=allocation['start']
        if start>cursor and any(raw[cursor:start]):
            gap=raw[cursor:start]
            # Corpus: short dword FF runs before palette/material/pointer cells.
            # Do not reinterpret arbitrary nonzero gaps or referenced payloads.
            if len(gap)>20 or len(gap)%4 or gap!=b'\xff'*len(gap) or any(cursor<=p<start for p in targets):
                raise ValueError('Unclassified nonzero YOBJ allocation gap')
            if not any(word in allocation['kind'] for word in ('palette','material','vertex pointer')):
                raise ValueError('FF fill has unverified allocation ownership')
            fills.append(dict(start=cursor,bytes=len(gap),value='ff',classification='INFERRED unreferenced allocation fill'))
        cursor=max(cursor,allocation['end'])
    if any(raw[cursor:model['report']['declared_yobj_end']]):raise ValueError('Unclassified trailing YOBJ data')
    return fills
