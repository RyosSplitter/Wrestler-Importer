"""Read-only audit of observed PSP YOBJ allocations and opaque mesh metadata."""
from collections import Counter
import hashlib
import math
import struct

from .yobj_read import Reader, _validate_hierarchy


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relocations(data):
    start = struct.unpack_from('<I', data, 4)[0]+8
    if data[start:start+4] != b'POF0':
        raise ValueError('Missing POF0')
    size = struct.unpack_from('<I', data, start+4)[0]
    if start+8+size != len(data):
        raise ValueError('POF0 allocation size mismatch')
    result, cursor, position = [], 8, start+8
    while position < len(data):
        first = data[position]
        if first == 0:
            if any(data[position:]):
                raise ValueError('Nonzero relocation data after padding')
            break
        width = {1: 1, 2: 2, 3: 4}.get(first >> 6)
        if not width or position+width > len(data):
            raise ValueError('Invalid relocation encoding')
        value = int.from_bytes(data[position:position+width], 'big')
        delta = (value & ((1 << (width*8-2))-1))*4
        if delta == 0:
            raise ValueError('Repeated POF0 relocation')
        cursor += delta
        if cursor+4 > start:
            raise ValueError('Relocation points outside YOBJ')
        result.append(cursor)
        position += width
    return result


def encode_relocations(locations):
    output, previous = bytearray(), 8
    for address in sorted(set(locations)):
        delta = address-previous
        if delta <= 0 or delta % 4:
            raise ValueError('Invalid relocation address')
        value = delta//4
        if value <= 63:
            output.append(value | 0x40)
        elif value <= 16383:
            output.extend(struct.pack('>H', value | 0x8000))
        elif value < (1 << 30):
            output.extend(struct.pack('>I', value | 0xC0000000))
        else:
            raise ValueError('Relocation delta overflow')
        previous = address
    return bytes(output)


def audit_yobj(data, *, allow_name_only=False):
    reader = Reader(data)
    if data[:4] != b'YOBJ':
        raise ValueError('Missing YOBJ')
    end = reader.u32(4)+8
    if reader.u32(12)+8 != end:
        raise ValueError('Declared YOBJ size fields disagree')
    reader.limit = end
    allocations, pointers = [], set()

    def span(start, size, kind, alignment=4):
        reader.check(start, size)
        if start % alignment:
            raise ValueError('Unaligned '+kind)
        allocations.append(dict(start=start, end=start+size, bytes=size, kind=kind))
        return data[start:start+size]

    def pointer(address):
        pointers.add(address)
        target = reader.u32(address)+8
        reader.check(target, 0)
        if target % 4:
            raise ValueError('Unaligned pointer target')
        return target

    def name(address):
        reader.check(address, 16)
        return data[address:address+16].split(b'\0', 1)[0].decode('cp932')

    span(0, 72, 'header')
    count, bone_count, texture_count = reader.unpack('<3I', 24)
    mesh_start, bone_start, texture_start, model_name_start = [pointer(a) for a in (36, 40, 44, 48)]
    span(mesh_start, count*64, 'mesh headers')
    bone_raw = span(bone_start, bone_count*80, 'bone table')
    texture_raw = span(texture_start, texture_count*16, 'texture names')
    if allow_name_only and model_name_start+16 == end:
        # Supplemental uploaded tool/reference file, not a native PAC sample.
        # This is deliberately opt-in; never used to relax trial validation.
        model_name_raw = span(model_name_start,16,'model name only')
        model_descriptor_raw = None
    else:
        model_descriptor_raw = span(model_name_start, 32, 'model name and descriptor')
        model_name_raw = model_descriptor_raw[:16]
        if reader.u32(model_name_start+24) != count:
            raise ValueError('Secondary descriptor mesh count disagrees')
    actual_reloc = relocations(data)
    # Some native accessory headers relocate a reserved zero-valued word.
    # Record it without inferring a new allocation or attachment meaning.
    if 60 in actual_reloc:
        pointer(60)
    bones = []
    for index in range(bone_count):
        a = bone_start+80*index
        local = reader.unpack('<4f', a+16)
        rotation = reader.unpack('<3f', a+32)
        global_position = reader.unpack('<3f', a+64)
        parent = reader.unpack('<i', a+48)[0]
        if not -1 <= parent < bone_count or not all(map(math.isfinite, (*local, *rotation, *global_position))):
            raise ValueError('Invalid bone record')
        bones.append(dict(index=index, name=name(a), parent=parent,
                          local_position=local[:3], local_w=local[3], rotation=rotation,
                          stored_global_position=global_position))
    _validate_hierarchy(bones)
    textures = [name(texture_start+i*16) for i in range(texture_count)]
    meshes, reports = [], []
    for index in range(count):
        a = mesh_start+index*64
        header = data[a:a+64]
        material_count, vertex_count = reader.u32(a+4), reader.u32(a+40)
        palette_start, material_start, cell = [pointer(a+v) for v in (8, 12, 24)]
        palette_count = reader.u32(palette_start+4)
        palette_header = span(palette_start, 16+4*palette_count, 'mesh %d palette'%index)
        if reader.u32(palette_start) != vertex_count:
            raise ValueError('Palette and mesh vertex counts differ')
        vertex_start = pointer(cell)
        span(cell, 4, 'mesh %d vertex pointer'%index)
        if pointer(palette_start+8) != vertex_start:
            raise ValueError('Vertex pointer aliases disagree')
        stored_palette = list(reader.unpack('<'+'I'*palette_count, palette_start+16))
        if any(not 1 <= b <= bone_count for b in stored_palette) or len(set(stored_palette)) != len(stored_palette):
            raise ValueError('Invalid/duplicate bone palette')
        palette = [b-1 for b in stored_palette]
        flag = reader.u32(a+28)
        base = flag & ~0x1C000
        rigid = flag == 0x11FF
        if rigid:
            slots, width, fmt, denominator = 0, 0, '', 1
        elif base in (0x17FF, 0x13FF, 0x15FF):
            slots = ((flag >> 14) & 7)+1
            if palette_count != slots or not 1 <= slots <= 8:
                raise ValueError('Invalid weighted palette layout')
            width, fmt, denominator = {0x17FF:(4,'f',1),0x13FF:(1,'B',128),0x15FF:(2,'H',32768)}[base]
        else:
            raise ValueError('Unsupported PSP GE layout '+hex(flag))
        weight_bytes = ((slots*width+3)//4)*4
        stride = 36+weight_bytes
        vertex_raw = span(vertex_start, vertex_count*stride, 'mesh %d vertices'%index)
        vertices = []
        sums, active = [], []
        for vi in range(vertex_count):
            va = vertex_start+vi*stride
            weights = [w/denominator for w in reader.unpack('<'+fmt*slots, va)] if slots else []
            uv = reader.unpack('<2f', va+weight_bytes)
            color = reader.unpack('<4B', va+weight_bytes+8)
            normal = reader.unpack('<3f', va+weight_bytes+12)
            position = reader.unpack('<3f', va+weight_bytes+24)
            if not all(map(math.isfinite, (*weights,*uv,*normal,*position))) or any(w<0 or w>1.0001 for w in weights):
                raise ValueError('Invalid vertex attributes')
            if slots and abs(sum(weights)-1) > .001:
                raise ValueError('Unnormalized skin weights')
            sums.append(sum(weights));active.append(sum(w>0 for w in weights))
            vertices.append(dict(weights=weights, uv=uv, color=color, normal=normal, position=position))
        span(material_start, 144*material_count, 'mesh %d materials'%index)
        materials, subreports = [], []
        for mi in range(material_count):
            ma = material_start+mi*144
            raw = data[ma:ma+144]
            tid = reader.unpack('<H', ma+22)[0]
            if tid >= texture_count:
                raise ValueError('Invalid texture index')
            strip_count, strip_start = reader.u32(ma+132), pointer(ma+136)
            first_index_start = pointer(ma+140)
            span(strip_start, 16*strip_count, 'mesh %d material %d strip headers'%(index,mi))
            strips, triangles, headers, index_ranges = [], [], [], []
            for si in range(strip_count):
                sa = strip_start+16*si
                length, ip = reader.u32(sa+8), pointer(sa+12)
                if not 1 <= length <= 65535:
                    raise ValueError('Invalid GE strip count')
                raw_indices = span(ip, 2*length, 'mesh %d material %d strip %d indices'%(index,mi,si))
                values = list(struct.unpack('<'+'H'*length, raw_indices))
                if any(v >= vertex_count for v in values):
                    raise ValueError('Index outside corresponding vertex buffer')
                for ti in range(length-2):
                    tri = (values[ti],values[ti+2],values[ti+1]) if ti%2 else tuple(values[ti:ti+3])
                    if len(set(tri)) == 3:
                        triangles.append(tri)
                strips.append(values);headers.append(data[sa:sa+16])
                index_ranges.append(dict(start=ip, bytes=len(raw_indices), indices=length,
                                         minimum=min(values), maximum=max(values), valid=True))
            if index_ranges and first_index_start != index_ranges[0]['start']:
                raise ValueError('Material first-index pointer alias disagrees')
            normalized = bytearray(raw);normalized[132:144]=bytes(12)
            materials.append(dict(texture_id=tid, control=reader.u32(ma+24), strips=strips,
                                  triangles=triangles, raw=raw, strip_headers=headers))
            subreports.append(dict(material=mi,texture_id=tid,texture=textures[tid],
                                   vertex_buffer_vertices=vertex_count,
                                   referenced_vertices=len(set(v for s in strips for v in s)),
                                   index_format='uint16',
                                   material_control=hex(reader.u32(ma+24)),
                                   opaque_render_state_hex=bytes(normalized).hex(),
                                   opaque_render_state_sha256=digest(normalized),
                                   triangles=len(triangles),indices=sum(map(len,strips)),
                                   strips=len(strips),index_ranges=index_ranges,
                                   strip_metadata=[h[:8].hex() for h in headers]))
        # Counts, pointers, palette-dependent GE count and bounding sphere are
        # mutable layout fields. All other mesh-header bytes are opaque state.
        opaque = bytearray(header)
        for start,length in [(4,12),(24,8),(40,4),(48,16)]:opaque[start:start+length]=bytes(length)
        struct.pack_into('<I',opaque,28,base)
        mesh = dict(index=index,flag=flag,base_flag=base,rigid=rigid,bone_palette=palette,
                    stored_bone_palette=stored_palette,vertices=vertices,materials=materials,
                    raw_header=header,raw_palette_header=palette_header,raw_vertices=vertex_raw,
                    stride=stride,weight_width=width,weight_slots=slots,opaque=bytes(opaque))
        meshes.append(mesh)
        reports.append(dict(mesh=index,vertices=vertex_count,
                            triangles=sum(len(m['triangles']) for m in materials),
                            indices=sum(len(s) for m in materials for s in m['strips']),
                            material_records=material_count,submeshes=subreports,
                            vertex_flag=hex(flag),vertex_stride=stride,
                            layout='weights, float UV, RGBA8, float normal, float position' if slots else 'rigid float UV, RGBA8, float normal, float position',
                            weight_format='none (rigid attachment semantics external)' if rigid else {4:'float32',2:'GE u16 /32768',1:'GE u8 /128'}[width],
                            weight_slots=slots,active_influences=dict(Counter(active)),
                            weight_sum_range=[min(sums),max(sums)] if slots else None,
                            bone_palette_zero_based=palette,bone_palette_stored_one_based=stored_palette,
                            bone_names=[bones[b]['name'] for b in palette],
                            opaque_mesh_metadata_hex=bytes(opaque).hex(),raw_mesh_header_hex=header.hex(),
                            bounds=list(reader.unpack('<4f',a+48)),
                            separation_rules=['Rigid/skinned vertex formats must remain distinct' if rigid else 'Combined palette must fit eight slots',
                                              'Preserve opaque mesh metadata, material state, strip metadata and draw order'],
                            vertex_buffer_start=vertex_start,vertex_buffer_bytes=len(vertex_raw)))
    if set(actual_reloc) != pointers:
        raise ValueError('POF0 does not match parsed pointer locations: missing %r extra %r'%
                         (sorted(pointers-set(actual_reloc)),sorted(set(actual_reloc)-pointers)))
    # Aliased four-byte vertex-pointer cells can be valid in native files.
    # Every nonempty allocation must otherwise be disjoint.
    ordered = sorted([a for a in allocations if a['bytes']],key=lambda a:(a['start'],a['end']))
    for previous,current in zip(ordered,ordered[1:]):
        if previous['end'] > current['start'] and not (previous['start']==current['start'] and previous['end']==current['end']):
            raise ValueError('Partially overlapping allocations: '+str((previous,current)))
    report = dict(model_name=name(model_name_start),meshes=count,bones=bone_count,textures=texture_count,
                  vertices=sum(len(m['vertices']) for m in meshes),
                  triangles=sum(r['triangles'] for r in reports),
                  material_records=sum(r['material_records'] for r in reports),
                  strips=sum(s['strips'] for r in reports for s in r['submeshes']),
                  indices=sum(r['indices'] for r in reports),
                  texture_names=textures,mesh_reports=reports,allocations=allocations,
                  relocation_count=len(actual_reloc),relocation_locations=actual_reloc,
                  declared_yobj_end=end,pof0_bytes=len(data)-end,expanded_bytes=len(data),
                  model_descriptor_hex=model_descriptor_raw.hex() if model_descriptor_raw else None,
                  offsets_ranges_indices_palettes_weights_valid=True)
    return dict(header=data[:72],bones=bones,texture_names=textures,
                bone_raw=bone_raw,texture_raw=texture_raw,model_name_raw=model_name_raw,
                model_descriptor_raw=model_descriptor_raw,
                meshes=meshes,report=report)
