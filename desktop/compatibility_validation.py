"""Compatibility repair primitives. A PSP base is evidence, not replacement art.

Do not infer anatomy, transfer weights, weld vertices or copy donor textures.
Every repair retains an explicit binary/pixel preservation check.
"""
import copy
import struct

import numpy as np

from desktop.edit_folder import quantize_rgba
from desktop.texture_optimizer.candidates import read_gim, write_gim, OBSERVED_DIMENSIONS, OBSERVED_T8_DIMENSIONS
from desktop.workspace import digest
from tools.pac_inspect import inspect_pac, parse_textures
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import verify, write_model
from tools.psp_mesh_merge_trial import sections
from tools.yobj_alignment import align_yobj_pof0
from tools.yukes_bpe import compress, decompress


def inventory(data):
    info=inspect_pac(data)
    if len({s['id'] for s in info['sections']})!=len(info['sections']):
        raise ValueError('Duplicate PAC section IDs cannot be resolved safely.')
    decoded={};errors=[];textures=[];models={};model_errors={};table_errors=[]
    for s in info['sections']:
        stored=data[s['offset']:s['offset']+s['size']]
        try:raw=decompress(stored) if stored.startswith(b'BPE ') else stored
        except Exception as exc:
            errors.append(f"Section {s['id']} cannot be decoded: {exc}");continue
        decoded[s['id']]=raw
        if raw.startswith(b'YOBJ'):
            try:models[s['id']]=audit_yobj(raw)
            except Exception as exc:model_errors[s['id']]=str(exc)
        if len(raw)>=16 and raw[4:16]==struct.pack('<3I',0x100,0,16):
            try:entries=parse_textures(raw)
            except ValueError as exc:
                table_errors.append(f"Texture table {s['id']}: {exc}");continue
            for e in entries:
                image=raw[e['offset']:e['offset']+e['size']]
                row=dict(section=s['id'],**e,raw=image,error=None,pixels=None,colors=None)
                try:
                    p,c=read_gim(image);row.update(pixels=p,colors=c)
                except (ValueError,IndexError,struct.error) as exc:row['error']=str(exc)
                textures.append(row)
    return dict(info=info,decoded=decoded,errors=errors,models=models,model_errors=model_errors,
                textures=textures,table_errors=table_errors)


def resolve(inv,name):
    choices=[t for t in inv['textures'] if t['name'].casefold()==name.casefold()]
    preferred=[t for t in choices if t['section']==9]
    choices=preferred or choices
    return choices[0] if len(choices)==1 else None


def texture_bits(row):
    if row.get('colors') is not None:return 4 if len(row['colors'])==16 else 8
    if len(row['raw'])>=78 and row['raw'][:12]==b'MIG.00.1PSP\0':
        fmt,order,w,h,bits=struct.unpack_from('<5H',row['raw'],68)
        if (fmt,bits) in ((4,4),(5,8)):return bits
    return None


def profile(base):
    inv=inventory(base)
    errors=list(inv['errors'])+inv['table_errors']+list(inv['model_errors'].values())
    if 2 not in inv['models']:errors.append('Base requires an audited PSP main YOBJ in section 2.')
    elif inv['models'][2]['report']['triangles']==0:errors.append('Base main model has no drawable triangles.')
    errors += [f"Base texture {t['name']}: {t['error']}" for t in inv['textures'] if t['error']]
    for model in inv['models'].values():
        for name in model['texture_names']:
            if resolve(inv,name) is None:errors.append('Base has missing or ambiguous texture '+name)
        for mesh in model['meshes']:
            for mat in mesh['materials']:
                t=resolve(inv,model['texture_names'][mat['texture_id']])
                if t and texture_bits(t):
                    expected=5 if texture_bits(t)==4 else 7
                    if mat['control'] not in (expected,expected|0x110):errors.append('Base has unsupported/mismatched material controls.')
    if errors:raise ValueError('PSP base is not a usable compatibility reference: '+'; '.join(errors))
    slots=sorted({len(m['bone_palette']) for model in inv['models'].values() for m in model['meshes'] if not m['rigid'] and m['base_flag']==0x17ff})
    result=dict(sha256=digest(base),bytes=len(base),model_sections=list(inv['models']),
        vertex_formats=sorted({hex(m['flag']) for model in inv['models'].values() for m in model['meshes']}),
        float_weight_slots=slots,material_controls=sorted({hex(a['control']) for model in inv['models'].values() for m in model['meshes'] for a in m['materials']}),
        texture_formats=sorted({texture_bits(t) for t in inv['textures']}),
        pixel_clut_bytes=sum(len(t['raw'])-208 for t in inv['textures']),
        texture_dimensions=sorted({(t['pixels'].shape[1],t['pixels'].shape[0]) for t in inv['textures']}),
        bone_names=[b['name'] for b in inv['models'][2]['bones']],
        policy='Compare format/rendering conventions. Different wrestler proportions, bone counts, mesh counts, material names and texture dimensions are not errors.')
    return inv,result


def recover_gim(raw):
    """Recover only the documented indexed layout with explicit bounded pixels.

    Supports padded LINEAR or swizzled input and redundant length-field repairs.
    No guessing pixel starts, dimensions, CLUT addresses, levels or color formats.
    """
    if len(raw)<128 or raw[:12]!=b'MIG.00.1PSP\0':raise ValueError('Unsupported texture signature; no pixels invented or copied from the base.')
    fmt,order,w,h,bits=struct.unpack_from('<5H',raw,68)
    if (fmt,bits) not in ((4,4),(5,8)) or order not in (0,1):raise ValueError('Unsupported indexed pixel layout.')
    if (w,h) not in OBSERVED_DIMENSIONS or (bits==8 and (w,h) not in OBSERVED_T8_DIMENSIONS):
        raise ValueError('No source-preserving target dimension/format in native evidence.')
    pitch=((w*bits+7)//8+15)//16*16;ph=(h+7)//8*8;end=128+pitch*ph
    if struct.unpack_from('<I',raw,64)[0]!=48 or 64+struct.unpack_from('<I',raw,112)[0]!=128:
        raise ValueError('Unsupported image header or independent first-frame address.')
    if struct.unpack_from('<4H',raw,104)!=(1,1,3,1):raise ValueError('Unsupported levels/frames; cannot flatten safely.')
    if end+80+(1<<bits)*4!=len(raw) or struct.unpack_from('<5H',raw,end+20)!=(3,0,1<<bits,1,32):
        raise ValueError('Truncated or unsupported RGBA32 palette; cannot reconstruct.')
    # Verify block identities before normalizing redundant chunk lengths.
    if any(struct.unpack_from('<HH',raw,a)!=(k,16) for a,k in ((16,2),(32,3),(48,4),(end,5))):
        raise ValueError('Unsupported GIM block hierarchy.')
    plane=np.frombuffer(raw[128:end],np.uint8).reshape(ph,pitch).copy()
    if order==1:
        y,x=np.indices((ph,pitch));address=((y//8)*(pitch//16)+x//16)*128+(y%8)*16+x%16
        plane=plane.reshape(-1)[address]
    if bits==4:
        p=np.empty((ph,pitch*2),np.uint8);p[:,::2]=plane&15;p[:,1::2]=plane>>4;p=p[:h,:w].copy()
    else:p=plane[:h,:w].copy()
    c=np.frombuffer(raw[end+80:],np.uint8).reshape(1<<bits,4).copy()
    # Preserve opaque header bytes and row padding; patch only known lengths,
    # pixel order and the pixel payload when necessary.
    fixed=bytearray(raw)
    for offset,value in ((20,len(raw)-16),(36,len(raw)-32),(52,80+pitch*ph),
                         (56,80+pitch*ph),(92,64),(96,end-64),
                         (end+4,80+c.size),(end+8,80+c.size)):
        struct.pack_into('<I',fixed,offset,value)
    if order==0:
        y,x=np.indices((ph,pitch));address=((y//8)*(pitch//16)+x//16)*128+(y%8)*16+x%16
        swizzled=np.empty(plane.size,np.uint8);swizzled[address]=plane
        fixed[128:end]=swizzled.tobytes();struct.pack_into('<H',fixed,70,1)
    q,d=read_gim(bytes(fixed))
    if not np.array_equal(p,q) or not np.array_equal(c,d):raise ValueError('GIM normalization changed pixels or palette.')
    return bytes(fixed),p,c,dict(kind='GIM layout/header normalization',original_order=order,
        rgba_exact=True,palette_exact=True,width=w,height=h,bits=bits)


def convert_depth(raw,p,c,bits):
    rgba=c[p];capacity=1<<bits
    if len(c)==capacity:return raw,dict(kind='depth unchanged',rgba_exact=True)
    palette=np.zeros((capacity,4),np.uint8)
    q,d,method=quantize_rgba(rgba,palette)
    result=write_gim(q,d,bits);a,b=read_gim(result)
    if not np.array_equal(b[a][:,:,3],rgba[:,:,3]):raise ValueError('Depth conversion changed alpha.')
    return result,dict(kind='GIM material-depth compatibility',bits=bits,
        rgba_exact=bool(np.array_equal(b[a],rgba)),alpha_exact=True,quantizer=method,
        rgb_rmse=float(np.sqrt(np.mean((b[a][:,:,:3].astype(float)-rgba[:,:,:3])**2))),
        dimensions=[p.shape[1],p.shape[0]],serialized_bytes=len(result))


def rebuild_table(raw,replacements):
    """Keep entry order, opaque fields, gaps and trailer; update offsets/sizes."""
    entries=parse_textures(raw);header_end=16+32*len(entries);out=bytearray(raw[:header_end]);cursor=header_end
    for e in sorted(entries,key=lambda r:r['offset']):
        out.extend(raw[cursor:e['offset']]);offset=len(out)
        image=replacements.get(e['index'],raw[e['offset']:e['offset']+e['size']])
        out.extend(image);cursor=e['offset']+e['size']
        struct.pack_into('<II',out,16+e['index']*32+20,len(image),offset)
        if e['index'] in replacements:out[16+e['index']*32+16:16+e['index']*32+20]=b'gim\0'
    out.extend(raw[cursor:]);parse_textures(bytes(out));return bytes(out)


def repair_model_metadata(raw):
    """Repair redundant aliases only when exactly one strict interpretation passes."""
    try:return raw,audit_yobj(raw),[]
    except (ValueError,IndexError,struct.error):pass
    def u32(data,a):
        if a<0 or a+4>len(data):raise ValueError('Truncated model metadata.')
        return struct.unpack_from('<I',data,a)[0]
    def patch(data,patches,a,value,why):
        old=u32(data,a)
        if old!=value:
            struct.pack_into('<I',data,a,value);patches.append(dict(offset=a,bytes=4,before=old,after=value,reason=why))
    if raw[:4]!=b'YOBJ' or len(raw)<72:raise ValueError('Missing YOBJ header.')
    ends={u32(raw,4)+8,u32(raw,12)+8}
    ends={end for end in ends if 72<=end<=len(raw)-8 and raw[end:end+4]==b'POF0'}
    if len(ends)!=1:raise ValueError('No unique verified duplicate-size/POF0 boundary.')
    end=ends.pop();common=bytearray(raw);initial=[]
    patch(common,initial,4,end-8,'YOBJ size alias agrees with uniquely located POF0 boundary')
    patch(common,initial,12,end-8,'Duplicate YOBJ size agrees with located POF0 boundary')
    patch(common,initial,end+4,len(common)-end-8,'Final POF0 length agrees with exact file bounds')
    meshes=u32(common,36)+8;descriptor=u32(common,48)+8
    if meshes<72 or descriptor<72 or descriptor+32>end:raise ValueError('Unrecoverable mesh/descriptor bounds.')
    counts={u32(common,24),u32(common,descriptor+24)}
    counts={count for count in counts if count and meshes+64*count<=end}
    accepted=[];failures=[]
    for count in sorted(counts):
        data=bytearray(common);patches=list(initial)
        patch(data,patches,24,count,'Mesh count alias selected by unique complete allocation/relocation audit')
        patch(data,patches,descriptor+24,count,'Descriptor count agrees with uniquely audited mesh array')
        try:
            for i in range(count):
                row=meshes+i*64;materials=u32(data,row+12)+8;nm=u32(data,row+4)
                if materials<72 or materials+144*nm>end:raise ValueError('Unrecoverable material bounds.')
                for j in range(nm):
                    ma=materials+144*j;ns=u32(data,ma+132);sa=u32(data,ma+136)+8
                    if sa<72 or sa+16*ns>end:raise ValueError('Unrecoverable strip-header bounds.')
                    if not ns:continue  # Preserve empty-record semantics; the strict reader decides validity.
                    ip=u32(data,sa+12)+8;n=u32(data,sa+8)
                    if ip<72 or ip+2*n>end:raise ValueError('Unrecoverable authoritative strip index range.')
                    patch(data,patches,ma+140,ip-8,'Redundant first-index alias agrees with bounded first strip')
            native=audit_yobj(bytes(data))
            if patches:accepted.append((bytes(data),native,patches))
        except (ValueError,IndexError,struct.error) as exc:failures.append(str(exc))
    if len(accepted)!=1:
        raise ValueError('No unique metadata-only repair passes the full audit: '+('; '.join(failures) or 'ambiguous or unrecoverable count aliases'))
    return accepted[0]


def patch_materials(raw,model,inv,base_controls):
    result=bytearray(raw);edits=[];mesh_array=struct.unpack_from('<I',raw,36)[0]+8
    for mesh in model['meshes']:
        materials=struct.unpack_from('<I',raw,mesh_array+mesh['index']*64+12)[0]+8
        for mi,mat in enumerate(mesh['materials']):
            name=model['texture_names'][mat['texture_id']];t=resolve(inv,name)
            bits=texture_bits(t) if t else None
            if bits is None:continue
            expected=5 if bits==4 else 7;old=mat['control'];desired=(old&~2)|(expected&2)
            if old in (5,7,0x115,0x117) and desired!=old and any((int(c,16)&~2)==(desired&~2) for c in base_controls):
                offset=materials+mi*144+24;struct.pack_into('<I',result,offset,desired)
                edits.append(dict(mesh=mesh['index'],material=mi,texture=name,offset=offset,
                                  before=hex(old),after=hex(desired),reason='Match existing texture depth; retain other rendering bits'))
    fixed=bytes(result);audit_yobj(fixed)
    return fixed,edits


def adapt_layout(raw,model,slots):
    """Zero-weight padding follows the base convention, never donor bone IDs."""
    selected=[m['index'] for m in model['meshes'] if not m['rigid'] and m['base_flag']==0x17ff and len(m['bone_palette'])==1]
    if not selected or not slots:return raw,[]
    target=min((n for n in slots if n>1),default=None)
    if target is None:return raw,[]
    from desktop.skinning import pad_mesh
    changed=copy.deepcopy(model)
    for i in selected:changed['meshes'][i]=pad_mesh(model['meshes'][i],model['bones'],target)
    groups=[[i] for i in range(len(model['meshes']))]
    result=write_model(changed,groups);proof=verify(raw,result,groups)
    # Exact effective weights/topology proof implies all analytical LBS poses
    # are unchanged. No facial-controller semantics are inferred from the base.
    return result,[dict(kind='base-compatible zero-weight slots',meshes=selected,slots=target,preservation=proof)]


def encode_section(raw,original,base):
    if not original.startswith(b'BPE ') and not base.startswith(b'BPE '):return raw
    encoded=min((compress(raw),compress(raw,max_distinct=220)),key=len)
    if decompress(encoded)!=raw:raise ValueError('BPE preservation check failed.')
    return encoded
