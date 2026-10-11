"""Reproduce priority-only A/B trials over a previously validated PSP baseline.

No geometry stage runs here. Inputs are never overwritten. Supply your own PACs.
"""
import argparse
import hashlib
import json
from pathlib import Path

from desktop.adapters import adapter
from desktop.accessories import source_models,decode_dependencies
from desktop.core import validate_pac
from desktop.texture_optimizer import optimize_pac
from desktop.texture_optimizer.candidates import read_gim
from tools.psp_mesh_merge_trial import sections


def run(source,baseline,output,names,adaptive=False,render=True,rebalance=False):
    source,baseline,output=map(Path,(source,baseline,output))
    if output.exists():raise FileExistsError('Refusing to overwrite experiment '+str(output))
    original=baseline.read_bytes();source_bytes=source.read_bytes()
    model,decoded=adapter('hctp').read(source)
    accessories,dependencies=source_models(source,model)
    decoded=decode_dependencies(source,decoded,dependencies)
    candidate,report=optimize_pac(original,decoded,output/'textures',priority_textures=names,
        freeze_unselected=not adaptive and not rebalance,rebalance_priorities=rebalance,
        progress=lambda m:print(m,flush=True))
    native,gims=validate_pac(candidate,gim_reader=read_gim)
    a={s['id']:raw for s,raw in sections(original)};b={s['id']:raw for s,raw in sections(candidate)}
    assert a.keys()==b.keys()
    for i in a:
        if i!=9:assert a[i]==b[i] # Includes retained tables after BPE roundtrip.
    assert baseline.read_bytes()==original and source.read_bytes()==source_bytes
    (output/'candidate.pac').write_bytes(candidate)
    if render:
        from desktop.preview import save_views
        from desktop.accessories import combined_preview
        from tools.psp_mesh_audit import audit_yobj
        for label,data in [('before',original),('after',candidate)]:
            main,images=validate_pac(data,gim_reader=read_gim)
            extras=[audit_yobj(raw) for s,raw in sections(data) if s['id']!=2 and raw.startswith(b'YOBJ')]
            folder=output/label;folder.mkdir()
            save_views(combined_preview(main,extras),images,folder,gim_reader=read_gim)
    summary=dict(source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        before_sha256=hashlib.sha256(original).hexdigest(),after_sha256=hashlib.sha256(candidate).hexdigest(),
        before_bytes=len(original),after_bytes=len(candidate),geometry_and_rigging_exact=True,
        native_validation='passed',pixel_palette_bytes=report['pixel_palette_bytes'],pixel_budget=report['pixel_palette_budget'],
        selected=[dict(name=r['name'],before=r['current_configuration'],after=r['selected_configuration'],
            improvement=r['priority_quality_improvement'],reductions=r['priority_reduction_report']) for r in report['textures'] if r['manual_priority']])
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('source');parser.add_argument('baseline');parser.add_argument('output')
    parser.add_argument('--select',nargs='+',required=True);parser.add_argument('--adaptive',action='store_true')
    parser.add_argument('--rebalance',action='store_true',help='Experimental priority/donor exchanges over the frozen model')
    parser.add_argument('--no-renders',action='store_true');args=parser.parse_args()
    summary=run(args.source,args.baseline,args.output,args.select,args.adaptive,not args.no_renders,args.rebalance)
    print(json.dumps({k:v for k,v in summary.items() if k!='selected'},indent=2),flush=True)
