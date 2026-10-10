"""Materialize reproducible follow-up configurations from a pinned search.

--search SEARCH.json selects the closest evaluated, uniform over-budget profile.
--face-only changes only the dominant cranial map's quantizer at existing size
and bit depth. Neither path processes geometry or changes the production app.
"""
import argparse
import copy
import json
from pathlib import Path

from app.ps2_textures import read_source
from tools.texture_convert import read_gim
from .frozen import FrozenPac,digest
from .metrics import compare,encode
from .optimizer import importance
from .trial import save_candidate


def run(source,baseline,output,search=None):
    output.mkdir(parents=True,exist_ok=False);frozen=FrozenPac(baseline.read_bytes())
    decoded=read_source(source,texture_names=frozen.names);rgba={n:p for i,n,r,p,d in decoded}
    entries=[];gims={}
    if search is not None:
        trace=json.loads(search.read_text())
        if trace['source_sha256']!=digest(source.read_bytes()) or trace['baseline_sha256']!=digest(baseline.read_bytes()):raise ValueError('Search input hashes differ')
        options=json.loads((search.parent/'options.json').read_text())['textures']
        selected=min((r for r in trace['evaluations'] if r['aspect_ratio_pass'] and not r['export_eligible']),key=lambda r:(r['pac_bytes'],r['weighted_loss']))
        for rows,index in zip(options,selected['selection']):
            entry=rows[index];name=entry['name']
            if entry['quantizer']=='Existing baseline':raw=frozen.gims[name]
            else:
                raw,_,check=encode(rgba[name],(entry['width'],entry['height']),entry['bits'])
                if len(raw)!=entry['encoded_bytes'] or abs(check['metrics']['loss']-entry['metrics']['loss'])>1e-12:raise ValueError('Quantizer replay differs')
            entries.append(entry);gims[name]=raw
        label='06-face8-over-budget'
    else:
        weights=importance(frozen,decoded)
        face=max(frozen.names,key=lambda n:weights[n]['head_fraction']*weights[n]['surface_area'])
        for i,name in enumerate(frozen.names):
            p,c=read_gim(frozen.gims[name]);bits=4 if len(c)==16 else 8
            entry=dict(name=name,index=i,source_dimensions=list(rgba[name].shape[1::-1]),width=p.shape[1],height=p.shape[0],bits=bits,palette_entries=len(c),encoded_bytes=len(frozen.gims[name]),pixel_palette_bytes=p.size*bits//8+c.size,quantizer='Existing accepted reduction',metrics=compare(rgba[name],c[p]))
            raw=frozen.gims[name]
            if name==face:
                raw,_,new=encode(rgba[name],(p.shape[1],p.shape[0]),bits);entry.update(new)
            entries.append(entry);gims[name]=raw
        label='07-face-quantizer-only'
    report=save_candidate(output,label,frozen,gims,entries)
    if search is not None and report['pac_bytes']!=selected['pac_bytes']:raise ValueError('Whole-PAC search replay differs')
    print(json.dumps({k:report[k] for k in ('label','pac_bytes','sha256','export_eligible')},indent=2),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--search',type=Path);g.add_argument('--face-only',action='store_true')
    a=p.parse_args();run(a.source,a.baseline,a.output,a.search)
