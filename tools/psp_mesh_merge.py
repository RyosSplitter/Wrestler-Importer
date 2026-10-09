"""Conservative, lossless mesh-buffer experiment for audited float-weight PSP YOBJ.

Only adjacent chunks with verified same-part provenance are considered. Material
and primitive records stay separate and ordered. No geometry reduction occurs.
Unknown mesh/palette fields must match; unknown material/strip bytes are copied.
This validates observed format semantics, not undocumented game-side limits.
"""
import math
import struct

from .psp_mesh_audit import audit_yobj, encode_relocations
from .yobj_alignment import align_yobj_pof0


def compatible(meshes, parts):
    reasons = []
    first = meshes[0]
    if any(m['rigid'] or m['base_flag'] != 0x17ff for m in meshes):
        reasons.append('Experiment supports only the observed float-weight skinned layout')
    if len(set(parts)) != 1:
        reasons.append('Different original target body parts; retained conservatively')
    if any(m['opaque'] != first['opaque'] for m in meshes):
        reasons.append('Different opaque mesh metadata')
    if any(m['raw_palette_header'][12:16] != first['raw_palette_header'][12:16] for m in meshes):
        reasons.append('Different opaque palette metadata')
    if len(set(b for m in meshes for b in m['bone_palette'])) > 8:
        reasons.append('Combined palette exceeds eight GE weight slots')
    if sum(len(m['vertices']) for m in meshes) > 65535:
        reasons.append('Combined vertex buffer exceeds conservative 16-bit range')
    if any(b['index'] != a['index']+1 for a,b in zip(meshes,meshes[1:])):
        reasons.append('Nonadjacent records; draw order retained conservatively')
    return reasons


def plan(model, parts):
    if len(parts) != len(model['meshes']):
        raise ValueError('Missing verified per-mesh body-part provenance')
    # Exhaust contiguous compatible partitions. Where two equally effective
    # merges overlap, choose the partition with less expanded vertex data.
    # No numerical mesh target is supplied or inferred from native references.
    meshes=model['meshes'];count=len(meshes)
    best={count:((0,0),[])}
    for start in range(count-1,-1,-1):
        choices=[]
        for end in range(start+1,count+1):
            candidates=meshes[start:end]
            if end>start+1 and compatible(candidates,parts[start:end]):break
            slots=len(set(b for m in candidates for b in m['bone_palette']))
            vertex_bytes=sum(len(m['vertices']) for m in candidates)*(36+4*slots)
            remainder,groups=best[end]
            choices.append(((1+remainder[0],vertex_bytes+remainder[1]),[list(range(start,end))]+groups))
        best[start]=min(choices,key=lambda x:x[0])
    return best[0][1]


def _enclosing_bounds(meshes):
    if len(meshes) == 1:
        return meshes[0]['raw_header'][48:64]
    bounds = [struct.unpack_from('<4f',m['raw_header'],48) for m in meshes]
    center = bounds[0][:3]
    needed = max(math.dist(center,b[:3])+b[3] for b in bounds)
    # Round upward, rather than inward, when storing the conservative union.
    radius = struct.unpack('<f',struct.pack('<f',needed))[0]
    if radius < needed:
        radius = struct.unpack('<f',struct.pack('<I',struct.unpack('<I',struct.pack('<f',radius))[0]+1))[0]
    return struct.pack('<4f',*center,radius)


def rebuild(data, groups, parts):
    model = audit_yobj(data)
    if model['model_descriptor_raw'] is None:
        raise ValueError('Missing native model descriptor; rewrite not authorized')
    cursor = 0
    for allocation in sorted(model['report']['allocations'],key=lambda a:a['start']):
        if allocation['start'] > cursor and any(data[cursor:allocation['start']]):
            raise ValueError('Unparsed nonzero data cannot be discarded safely')
        cursor = max(cursor,allocation['end'])
    if any(data[cursor:model['report']['declared_yobj_end']]):
        raise ValueError('Unparsed nonzero trailing data cannot be discarded safely')
    if [i for g in groups for i in g] != list(range(len(model['meshes']))):
        raise ValueError('Groups must preserve every mesh exactly once in order')
    for group in groups:
        if len(group)>1:
            reasons = compatible([model['meshes'][i] for i in group],[parts[i] for i in group])
            if reasons:
                raise ValueError('; '.join(reasons))
    out = bytearray(model['header'])
    relocation_locations = []

    def allocate(raw, alignment=16):
        # YOBJ pointer origin is byte 8. All buffers in the selected source
        # and native PAC references align to that origin, not file byte zero.
        out.extend(bytes((-(len(out)-8))%alignment))
        address = len(out)
        out.extend(raw)
        return address

    def u32(address,value):
        struct.pack_into('<I',out,address,value)

    def ptr(address,target):
        if target < 8 or target%4:
            raise ValueError('Invalid output pointer')
        u32(address,target-8)
        relocation_locations.append(address)

    mesh_array = allocate(bytes(64*len(groups)))
    ptr(36,mesh_array);u32(24,len(groups))
    # The selected Lance input has no unknown relocated header word.
    if 60 in model['report']['relocation_locations']:
        raise ValueError('Unknown relocated header field cannot be rewritten safely')
    for gi,group in enumerate(groups):
        meshes = [model['meshes'][i] for i in group]
        first = meshes[0]
        palette = list(dict.fromkeys(b for m in meshes for b in m['bone_palette']))
        if first['base_flag'] != 0x17ff or first['rigid']:
            raise ValueError('Only float32 skinned source supported by this writer')
        raw_vertices = bytearray()
        for mesh in meshes:
            slot_map = [palette.index(b) for b in mesh['bone_palette']]
            for vi in range(len(mesh['vertices'])):
                raw = mesh['raw_vertices'][vi*mesh['stride']:(vi+1)*mesh['stride']]
                weights = bytearray(4*len(palette))
                for old,new in enumerate(slot_map):
                    weights[4*new:4*new+4] = raw[4*old:4*old+4]
                raw_vertices.extend(weights+raw[4*mesh['weight_slots']:])
        n = sum(len(m['vertices']) for m in meshes)
        mats = [(m,material) for m in meshes for material in m['materials']]
        a = mesh_array+gi*64
        out[a:a+64] = first['raw_header']
        u32(a+4,len(mats));u32(a+40,n)
        u32(a+28,0x17ff|((len(palette)-1)<<14))
        out[a+48:a+64] = _enclosing_bounds(meshes)
        ph = allocate(struct.pack('<3I',n,len(palette),0)+first['raw_palette_header'][12:16]+struct.pack('<'+'I'*len(palette),*[b+1 for b in palette]))
        cell = allocate(bytes(4))
        vp = allocate(raw_vertices)
        ptr(a+8,ph);ptr(a+24,cell);ptr(cell,vp);ptr(ph+8,vp)
        ma = allocate(b''.join(mat['raw'] for _,mat in mats))
        ptr(a+12,ma)
        bases,offset = {},0
        for mesh in meshes:
            bases[mesh['index']]=offset
            offset+=len(mesh['vertices'])
        strip_arrays=[]
        for mi,(mesh,material) in enumerate(mats):
            if not material['strips']:
                raise ValueError('Empty material index alias semantics unknown')
            sa = allocate(b''.join(material['strip_headers']))
            ptr(ma+mi*144+136,sa)
            strip_arrays.append(sa)
        for mi,(mesh,material) in enumerate(mats):
            sa=strip_arrays[mi]
            for si,strip in enumerate(material['strips']):
                values = [v+bases[mesh['index']] for v in strip]
                if any(v>=n or v>65535 for v in values):
                    raise ValueError('Remapped index out of range')
                ip = allocate(struct.pack('<'+'H'*len(values),*values))
                ptr(sa+si*16+12,ip)
                if si == 0:
                    ptr(ma+mi*144+140,ip)
    # Preserve the source's mesh-first / bones / textures / descriptor order.
    ptr(40,allocate(model['bone_raw']))
    ptr(44,allocate(model['texture_raw']))
    descriptor = bytearray(model['model_descriptor_raw'])
    struct.pack_into('<I',descriptor,24,len(groups))
    ptr(48,allocate(descriptor))
    u32(4,len(out)-8);u32(12,len(out)-8)
    relocation = encode_relocations(relocation_locations)
    out.extend(b'POF0'+struct.pack('<I',len(relocation))+relocation)
    result = align_yobj_pof0(bytes(out))
    audit = audit_yobj(result)
    for mesh in audit['report']['mesh_reports']:
        if (mesh['vertex_buffer_start']-8)%16:
            raise ValueError('Vertex buffer alignment differs from source convention')
        for material in mesh['submeshes']:
            if any((r['start']-8)%16 for r in material['index_ranges']):
                raise ValueError('Index buffer alignment differs from source convention')
    return result


def _semantic(model):
    vertices,materials,strips,triangles = [],[],[],[]
    offset = 0
    for mesh in model['meshes']:
        for vi in range(len(mesh['vertices'])):
            raw = mesh['raw_vertices'][vi*mesh['stride']:(vi+1)*mesh['stride']]
            weights = {b:raw[s*4:s*4+4] for s,b in enumerate(mesh['bone_palette'])
                       if struct.unpack_from('<f',raw,s*4)[0]!=0}
            vertices.append((raw[4*mesh['weight_slots']:],weights))
        for material in mesh['materials']:
            materials.append(material['raw'][:132])
            strips.extend((h[:8],tuple(v+offset for v in s)) for h,s in zip(material['strip_headers'],material['strips']))
            triangles.extend(tuple(v+offset for v in t) for t in material['triangles'])
        offset+=len(mesh['vertices'])
    return vertices,materials,strips,triangles


def verify(before,after,groups):
    a,b = audit_yobj(before),audit_yobj(after)
    for key in ('bone_raw','texture_raw','model_name_raw'):
        if a[key]!=b[key]:raise ValueError(key+' changed')
    if a['model_descriptor_raw'][:24]!=b['model_descriptor_raw'][:24] or a['model_descriptor_raw'][28:]!=b['model_descriptor_raw'][28:]:
        raise ValueError('Non-count model descriptor metadata changed')
    ha,hb = bytearray(a['header']),bytearray(b['header'])
    for offset in (4,12,24,36,40,44,48):
        ha[offset:offset+4]=hb[offset:offset+4]=bytes(4)
    if ha != hb:raise ValueError('Non-layout model header metadata changed')
    if _semantic(a)!=_semantic(b):
        raise ValueError('Geometry, per-bone weight bits, render state or ordered primitives changed')
    for mesh,group in zip(b['meshes'],groups):
        originals = [a['meshes'][i] for i in group]
        if mesh['opaque']!=originals[0]['opaque']:
            raise ValueError('Opaque mesh metadata changed')
        if mesh['raw_palette_header'][12:16]!=originals[0]['raw_palette_header'][12:16]:
            raise ValueError('Opaque palette metadata changed')
        center,radius = struct.unpack_from('<3ff',mesh['raw_header'],48)[:3],struct.unpack_from('<f',mesh['raw_header'],60)[0]
        for old in originals:
            x,y,z,r = struct.unpack_from('<4f',old['raw_header'],48)
            if math.dist(center,(x,y,z))+r>radius+1e-6:
                raise ValueError('New culling sphere excludes an original sphere')
        if len(group)==1 and mesh['raw_header'][48:64]!=originals[0]['raw_header'][48:64]:
            raise ValueError('Unmerged bounds changed')
    return dict(vertex_suffix_bits_identical=True,per_bone_nonzero_weight_bits_identical=True,
                ordered_global_indices_and_triangle_winding_identical=True,
                ordered_material_state_and_strip_metadata_identical=True,
                skeleton_texture_names_model_name_byte_identical=True,
                secondary_model_descriptor_count_matches_mesh_count=True,
                opaque_mesh_palette_model_metadata_identical=True,
                unmerged_bounds_identical_and_merged_bounds_enclose_original_spheres=True,
                before_and_after_allocation_palette_index_weight_relocation_audit_passed=True)
