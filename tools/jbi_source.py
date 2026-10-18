"""Bounded JBI source selection and verified independent-model contracts.

The DPAC/TIM2 primitives retain their historical ``sym_*`` module names. The
owner corrected that sample's provenance to JBI; this is not a SYM adapter.
No character name or file hash chooses decoding or conversion behavior.
"""
import copy
import re

import numpy as np

from tools.hctp_weights import read_hctp_with_weights
from tools.pac_inspect import inspect_pac
from tools.psp_mesh_merge_trial import sections
from tools.sym_atlas import partition
from tools.sym_rig import arrays
from tools.sym_source import read_atlas, read_ch_directory, sha

MAX_INPUT_BYTES=32*1024*1024


def select(data, entry_id=''):
    if not isinstance(entry_id,str) or (entry_id and not re.fullmatch('[0-9a-fA-F]{4}',entry_id)):
        raise ValueError('JBI archive entry must be a four-digit hexadecimal ID.')
    if not data or len(data)>MAX_INPUT_BYTES:
        raise ValueError('Choose a JBI PAC within the 32 MiB input budget.')
    if data[:4]==b'DPAC':
        directory=read_ch_directory(data)
        selected=entry_id.lower() or directory['entries'][0]['id_hex']
        entry=next((e for e in directory['entries'] if e['id_hex']==selected),None)
        if entry is None:raise ValueError('JBI archive has no entry '+selected)
        raw=data[entry['offset']:entry['offset']+entry['stored_bytes']]
        return raw,dict(container='DPAC',selected_entry=selected,
            entries=[dict(id=e['id_hex'],bytes=e['stored_bytes']) for e in directory['entries']],
            source_sha256=sha(data),entry_sha256=sha(raw),entry_bytes=len(raw))
    if data[:4]!=b'PAC ':
        raise ValueError('Choose a supported JBI CH.PAC archive or an extracted JBI costume PAC.')
    if entry_id:raise ValueError('An extracted JBI PAC has no archive entry selector.')
    inspect_pac(data)
    return data,dict(container='PAC',selected_entry='',entries=[],source_sha256=sha(data),
                     entry_sha256=sha(data),entry_bytes=len(data))


def decode(raw):
    info=inspect_pac(raw)
    if len({s['id'] for s in info['sections']})!=len(info['sections']):
        raise ValueError('Duplicate JBI section IDs cannot identify model roles.')
    decoded={s['id']:payload for s,payload in sections(raw)}
    model_ids={sid for sid,payload in decoded.items() if payload.startswith(b'YOBJ')}
    if 2 not in model_ids:raise ValueError('JBI costume has no supported main YOBJ in section 2.')
    if model_ids-{2,6,7}:
        raise ValueError('Unsupported JBI accessory YOBJ section(s): '+', '.join(map(str,sorted(model_ids-{2,6,7})))+
                         '. These objects cannot yet be converted; no model was silently omitted.')
    if 1 not in decoded or not decoded[1].startswith(b'TIM2'):
        raise ValueError('JBI requires its original TIM2 atlas in section 1. For HCTP files, select Here Comes the Pain.')
    originals={sid:read_hctp_with_weights(decoded[sid]) for sid in sorted(model_ids)}
    main=originals[2]
    combined=copy.deepcopy(main);combined['meshes']=[];roles=[]
    for sid,model in originals.items():
        if model['textures']!=main['textures'] or len(model['bones'])!=len(main['bones']):
            raise ValueError('JBI accessory atlas or bone-table size differs from the main model.')
        for a,b in zip(model['bones'],main['bones']):
            if any(a[k]!=b[k] for k in ('name','parent','local_position','rotation')):
                raise ValueError('JBI accessory local rig differs from the main model.')
        points,weights=arrays(model)
        support=[b['name'] for b in model['bones'] if np.any(weights[:,b['index']]>1e-7)]
        if sid in (6,7):
            side='l' if sid==6 else 'r'
            if not support or any(not n.startswith(side+'_') or not any(stem in n for stem in ('kote','ninoude')) for n in support):
                raise ValueError('JBI section %d does not match the verified unilateral elbow-pad contract.'%sid)
        roles.append(dict(section=sid,vertices=len(points),triangles=model['triangle_count'],support=support,
            bounds=[points.min(0).tolist(),points.max(0).tolist()],sha256=sha(decoded[sid])))
        for mesh in copy.deepcopy(model['meshes']):
            mesh['source_section']=sid;mesh['index']=len(combined['meshes']);combined['meshes'].append(mesh)
    combined.update(mesh_count=len(combined['meshes']),
        triangle_count=sum(m['triangle_count'] for m in originals.values()),
        vertex_count=sum(m['vertex_count'] for m in originals.values()),
        source_vertex_count=sum(m['source_vertex_count'] for m in originals.values()))
    pixels,palette,atlas_format=read_atlas(decoded[1])
    charted,images,atlas_report=partition(combined,palette[pixels])
    return dict(originals=originals,charted=charted,images=images,atlas=atlas_report,
                atlas_format=atlas_format,source_roles=roles)


def read(data,entry_id=''):
    raw,selection=select(data,entry_id)
    try:bundle=decode(raw)
    except ValueError as exc:
        label=' entry '+selection['selected_entry'] if selection['selected_entry'] else ''
        raise ValueError('JBI'+label+': '+str(exc)) from exc
    return dict(bundle,selection=selection)


def decoded_textures(bundle):
    return [(i,n,b'',image,dict(bundle['atlas_format'],atlas_chart=bundle['atlas']['islands'][i]))
            for i,(n,image) in enumerate(zip(bundle['charted']['textures'],bundle['images']))]
