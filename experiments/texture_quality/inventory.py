"""Read-only SVR PSP PAC/GIM census. No native assets are copied to reports.

python -m experiments.texture_quality.inventory --inputs INPUTS.json --output NEW_DIR
INPUTS.json is a list of {filename, path} records pointing to user-owned PACs.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import struct

from tools.pac_inspect import inspect_pac, parse_textures
from tools.psp_mesh_audit import audit_yobj
from tools.texture_convert import read_gim
from tools.yukes_bpe import decompress
from .gim import read_native_gim


def sha(data):
    return hashlib.sha256(data).hexdigest()


def gim_info(data):
    if len(data) < 128 or data[:12] != b'MIG.00.1PSP\0':
        raise ValueError('Missing supported GIM signature/header')
    if struct.unpack_from('<I', data, 20)[0] + 16 != len(data):
        raise ValueError('GIM root size mismatch')
    fmt, order, width, height, bits, pitch, vertical, unknown = struct.unpack_from('<8H', data, 68)
    block_size = struct.unpack_from('<I', data, 52)[0]
    palette_start = 48 + block_size
    pixel_start = 64 + struct.unpack_from('<I', data, 92)[0]
    pixel_end = 64 + struct.unpack_from('<I', data, 96)[0]
    if not width or not height or not 128 <= pixel_start <= pixel_end <= palette_start <= len(data)-80:
        raise ValueError('GIM image/palette pointers outside allocation')
    pformat, porder, pw, ph, pbits = struct.unpack_from('<5H', data, palette_start+20)
    palette_size = struct.unpack_from('<I', data, palette_start+4)[0]
    if palette_start+palette_size != len(data):
        raise ValueError('GIM palette allocation mismatch')
    palette_data = palette_start+16+struct.unpack_from('<I', data, palette_start+44)[0]
    if not palette_start+80 <= palette_data <= len(data):
        raise ValueError('GIM palette data pointer outside allocation')
    actual_palette = len(data)-palette_data
    nominal_pixels = (width*height*bits+7)//8
    row_bytes = (width*bits+7)//8
    padded_pixels = ((row_bytes+15)//16*16)*((height+7)//8*8)
    row = dict(encoded_bytes=len(data),sha256=sha(data),format=fmt,order=order,
               width=width,height=height,aspect_ratio=width/height,bits=bits,
               pitch_alignment=pitch,vertical_alignment=vertical,unknown_info_value=unknown,
               image_block_bytes=block_size,image_data_offset=pixel_start,
               image_data_end=pixel_end,image_allocation_bytes=palette_start-pixel_start,
               nominal_pixel_bytes=nominal_pixels,padded_swizzle_pixel_bytes=padded_pixels,
               palette_block_offset=palette_start,palette_block_bytes=palette_size,
               palette_format=pformat,palette_order=porder,palette_width=pw,palette_height=ph,
               palette_bits=pbits,palette_entries=pw*ph,palette_data_offset=palette_data,
               palette_bytes=actual_palette,
               stored_pixel_palette_bytes=palette_start-pixel_start+actual_palette,
               modeled_gpu_pixel_palette_bytes=padded_pixels+actual_palette,
               runtime_allocation_scope='Pixel/CLUT data estimate; excludes allocator, loader, duplicate uploads and caches',
               level_type=struct.unpack_from('<H',data,104)[0],
               level_count=struct.unpack_from('<H',data,106)[0],
               frame_type=struct.unpack_from('<H',data,108)[0],
               frame_count=struct.unpack_from('<H',data,110)[0])
    try:
        indices, palette = read_gim(data)
        row.update(writer_subset_decodable=True,alpha_range=[int(palette[indices][:,:,3].min()),int(palette[indices][:,:,3].max())],
                   used_palette_entries=len(set(indices.ravel().tolist())))
    except (ValueError, struct.error) as exc:
        row.update(writer_subset_decodable=False,decoder_limitation=str(exc))
    try:
        indices,palette=read_native_gim(data)
        if row['writer_subset_decodable']:
            a,b=read_gim(data)
            if not ((a==indices).all() and (b==palette).all()):raise ValueError('Native decoder disagrees with existing subset')
        row.update(research_decoder_pass=True,alpha_range=[int(palette[indices][:,:,3].min()),int(palette[indices][:,:,3].max())],used_palette_entries=len(set(indices.ravel().tolist())))
    except ValueError as exc:row.update(research_decoder_pass=False,research_decoder_error=str(exc))
    return row


def scan(record):
    data = Path(record['path']).read_bytes()
    result=dict(filename=record['filename'],sha256=sha(data),pac_bytes=len(data),textures=[],sections=[],models=[],errors=[])
    info=inspect_pac(data)
    result.update(pac_aligned_2048=len(data)%2048==0,section_offsets_aligned_16=all(s['offset']%16==0 for s in info['sections']),section_offsets_aligned_4=all(s['offset']%4==0 for s in info['sections']))
    stored_by_kind=Counter();decoded_by_kind=Counter()
    def classify(raw,path):
        if raw.startswith(b'YOBJ'):
            try:
                model=audit_yobj(raw)
                result['models'].append(dict(section_path=path,decoded_bytes=len(raw),mesh_count=model['report']['meshes'],vertex_count=model['report']['vertices'],triangle_count=model['report']['triangles'],bone_count=model['report']['bones'],
                      texture_names=model['texture_names'],material_controls=[dict(mesh=m['index'],texture=model['texture_names'][mat['texture_id']],control=mat['control']) for m in model['meshes'] for mat in m['materials']]))
            except (ValueError,KeyError,struct.error) as exc:
                count,bones,textures=struct.unpack_from('<3I',raw,24)
                descriptor=struct.unpack_from('<I',raw,48)[0]+8
                result['errors'].append(dict(section_path=path,scope='strict converted-YOBJ parser coverage; not a claim that native asset is malformed',message=str(exc),header_mesh_count=count,header_bone_count=bones,header_texture_count=textures,secondary_descriptor_count=struct.unpack_from('<I',raw,descriptor+24)[0] if descriptor+28<=len(raw) else None))
            return 'model'
        if len(raw)>=16 and raw[4:16]==struct.pack('<3I',256,0,16):
            for entry in parse_textures(raw):
                g=raw[entry['offset']:entry['offset']+entry['size']]
                row=dict(section_path=path,name=entry['name'],table_offset=entry['offset'],table_alignment_16=entry['offset']%16==0)
                try:row.update(gim_info(g))
                except (ValueError,struct.error) as exc:row.update(error=str(exc),encoded_bytes=len(g),sha256=sha(g))
                result['textures'].append(row)
            return 'textures'
        if raw.startswith(b'PAC '):
            for section in inspect_pac(raw)['sections']:
                payload=raw[section['offset']:section['offset']+section['size']]
                child=decompress(payload) if payload.startswith(b'BPE ') else payload
                classify(child,path+'/'+str(section['id']))
            return 'nested_other'
        return 'other'
    for section in info['sections']:
        payload=data[section['offset']:section['offset']+section['size']]
        raw=decompress(payload) if payload.startswith(b'BPE ') else payload
        kind=classify(raw,str(section['id']))
        result['sections'].append(dict(id=section['id'],offset=section['offset'],stored_bytes=len(payload),decoded_bytes=len(raw),kind=kind,compressed=payload.startswith(b'BPE ')))
        stored_by_kind[kind]+=len(payload);decoded_by_kind[kind]+=len(raw)
    result.update(stored_allocation=dict(stored_by_kind),decoded_allocation=dict(decoded_by_kind),
                  container_header_padding_bytes=len(data)-sum(stored_by_kind.values()))
    good=[t for t in result['textures'] if 'error' not in t]
    result.update(texture_count=len(result['textures']),unique_texture_payloads=len({t['sha256'] for t in result['textures']}),
                  encoded_gim_bytes=sum(t['encoded_bytes'] for t in good),
                  stored_pixel_palette_bytes=sum(t['stored_pixel_palette_bytes'] for t in good),
                  modeled_gpu_pixel_palette_bytes=sum(t['modeled_gpu_pixel_palette_bytes'] for t in good))
    by_texture={t['name']:t for t in good if t['section_path']=='9'}
    result['material_texture_pairs']=[dict(texture=r['texture'],control=hex(r['control']),bits=by_texture[r['texture']]['bits'])
        for m in result['models'] for r in m['material_controls'] if r['texture'] in by_texture]
    return result


def run(inputs,output,workers=4):
    output.mkdir(parents=True,exist_ok=False)
    records=json.loads(inputs.read_text())
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows=list(pool.map(scan,records))
    textures=[dict(pac=row['filename'],**t) for row in rows for t in row['textures']]
    good=[t for t in textures if 'error' not in t]
    def counts(values):return dict(sorted(Counter(values).items()))
    def ranges(key):
        v=[r[key] for r in rows];return dict(minimum=min(v),maximum=max(v),mean=sum(v)/len(v))
    summary=dict(classification='CONFIRMED: uploaded corpus observations; not universal loader limits',pac_count=len(rows),
                 unique_pac_hashes=len({r['sha256'] for r in rows}),texture_records=len(textures),
                 unique_gim_hashes=len({t['sha256'] for t in textures}),
                 dimensions=counts('%dx%d'%(t['width'],t['height']) for t in good),
                 image_formats=counts(str(t['format']) for t in good),bits=counts(str(t['bits']) for t in good),
                 palette_formats=counts(str(t['palette_format']) for t in good),
                 palette_entries=counts(str(t['palette_entries']) for t in good),
                 pixel_orders=counts(str(t['order']) for t in good),
                 palette_orders=counts(str(t['palette_order']) for t in good),
                 image_levels=counts(str(t['level_count']) for t in good),
                 all_native_texture_records_decoded=all(t.get('research_decoder_pass') for t in textures),
                 outer_pac_alignment_2048_count=sum(r['pac_aligned_2048'] for r in rows),
                 all_outer_sections_alignment_4_count=sum(r['section_offsets_aligned_4'] for r in rows),
                 all_outer_sections_alignment_16_count=sum(r['section_offsets_aligned_16'] for r in rows),
                 texture_payload_alignment_16_count=sum(t['table_alignment_16'] for t in good),
                 pac_bytes=ranges('pac_bytes'),texture_counts=ranges('texture_count'),encoded_gim_bytes=ranges('encoded_gim_bytes'),
                 modeled_gpu_pixel_palette_bytes=ranges('modeled_gpu_pixel_palette_bytes'),
                 writer_subset_decoder_failures=[dict(pac=t['pac'],name=t['name'],width=t['width'],height=t['height'],message=t.get('decoder_limitation',t.get('error'))) for t in textures if not t.get('writer_subset_decodable')],
                 model_audit_failures=[dict(pac=r['filename'],**e) for r in rows for e in r['errors']],
                 material_texture_pairs=counts('%s/%s'%(p['bits'],p['control']) for r in rows for p in r['material_texture_pairs']))
    (output/'inventory.json').write_text(json.dumps(dict(summary=summary,pacs=rows),indent=2)+'\n')
    with (output/'textures.csv').open('w',newline='') as f:
        keys=sorted({k for t in textures for k in t});w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(textures)
    with (output/'pacs.csv').open('w',newline='') as f:
        keys=['filename','sha256','pac_bytes','texture_count','encoded_gim_bytes','stored_pixel_palette_bytes','modeled_gpu_pixel_palette_bytes','stored_model_bytes','stored_texture_bytes','decoded_model_bytes','decoded_texture_bytes']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for r in rows:w.writerow({**{k:r[k] for k in keys[:7]},'stored_model_bytes':r['stored_allocation'].get('model',0),'stored_texture_bytes':r['stored_allocation'].get('textures',0),'decoded_model_bytes':r['decoded_allocation'].get('model',0),'decoded_texture_bytes':r['decoded_allocation'].get('textures',0)})
    print(json.dumps(summary,indent=2),flush=True)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();run(args.inputs,args.output,args.workers)
