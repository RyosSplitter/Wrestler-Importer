"""Reproduce native palette observations without distributing game assets."""
import argparse
from collections import Counter
import json
from pathlib import Path

from model_qa.geometry import read_model,sha


def inventory(root):
    rows=[];skipped=[];weighted=Counter();rigid=Counter()
    # Match the explicitly bounded reference subset used in the head study.
    for path in sorted(Path(root).glob('*/*.PAC')):
        try:model=read_model(path)
        except (ValueError,KeyError,IndexError,RuntimeError) as exc:
            skipped.append(dict(file=str(path),reason=str(exc)));continue
        meshes=[]
        for mesh in model['meshes']:
            count=len(mesh['bone_palette']);(rigid if mesh['rigid'] else weighted)[count]+=1
            meshes.append(dict(mesh=mesh['index'],rigid=mesh['rigid'],weight_slots=count,
                               flag=hex(mesh['flag']),stride=mesh['stride'],vertices=len(mesh['vertices'])))
        rows.append(dict(file=str(path),sha256=sha(path),meshes=meshes))
    return dict(scope='Uppercase *.PAC one directory below root, successfully supported by current strict auditor; not the entire native corpus.',
        audited_files=len(rows),weighted_palette_histogram=dict(weighted),rigid_palette_histogram=dict(rigid),
        files=rows,skipped=skipped,interpretation='Observed native conventions, not proven hard loader limits.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    r=inventory(a.root);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k] for k in ('audited_files','weighted_palette_histogram','rigid_palette_histogram')}))
