"""Package immutable before/after reports and a YOBJ experiment, never a PAC."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image
from tools.pac_inspect import parse_textures
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections,write_preview
from tools.texture_convert import read_gim


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(before,after,trial,gate,baseline,output,archive,title,region,views,evidence):
    before,after,trial,gate,baseline,output,archive=map(Path,(before,after,trial,gate,baseline,output,archive))
    if output.exists() or archive.exists():raise FileExistsError('Refusing to replace an experiment')
    data=json.loads(gate.read_text());old=json.loads((before/'report.json').read_text());new=json.loads((after/'report.json').read_text())
    if new['preserved_previous_candidate_sha256']!=sha(trial/'candidate.yobj'):raise ValueError('QA report does not match experimental YOBJ')
    if old['preserved_previous_candidate_sha256']!=sha(baseline):raise ValueError('Baseline PAC identity mismatch')
    output.mkdir(parents=True)
    shutil.copytree(before,output/'before');shutil.copytree(after,output/'after');shutil.copytree(trial,output/'trial')
    shutil.copy2(gate,output/'acceptance.json');(output/'evidence').mkdir()
    for name,path in evidence:shutil.copy2(path,output/'evidence'/name)
    preview=output/'preview';preview.mkdir();raw=(trial/'candidate.yobj').read_bytes();model=audit_yobj(raw)
    shutil.copy2(trial/'candidate.yobj',preview/'candidate.yobj');write_preview(model,preview/'candidate.obj')
    textures={t['name']:raw[t['offset']:t['offset']+t['size']] for s,raw in sections(baseline.read_bytes()) if s['id'] in (8,9) for t in parse_textures(raw)}
    mtl=[]
    for i,name in enumerate(model['texture_names']):
        gim=textures[name];pixels,palette=read_gim(gim);(preview/(name+'.gim')).write_bytes(gim)
        Image.fromarray(palette[pixels]).save(preview/(name+'.png'));mtl.extend(['newmtl texture_%d'%i,'Kd 1 1 1','map_Kd '+name+'.png'])
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    e=html.escape
    text='''<!doctype html><html><head><meta charset="utf-8"><title>QA experiment</title><style>body{font:16px system-ui;background:#202329;color:#ddd;max-width:1300px;margin:25px auto;padding:18px}a{color:#8ecaff}img{width:100%}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #555}</style></head><body><h1>'''+e(title)+'''</h1><p>Isolated experiment: accepted PAC baseline and QA code are unchanged. No PAC was constructed or repacked. Candidate YOBJ and unchanged textures are in preview/. CPU clay comparison renders are not Noesis/game screenshots. Animation checks are analytical LBS, not actual gameplay.</p>
<p><a href="before/report.html">Before: full baseline QA</a> · <a href="after/report.html">After: full experimental QA</a> · <a href="acceptance.json">Regression/format gate</a> · <a href="trial/experiment.json">Exact change evidence</a></p><table><tr><th>Region/pose</th><th>Before p95 / height</th><th>After p95 / height</th></tr>'''
    for m in data['improvements']:text+='<tr><td>'+e(m['region']+' / '+m['pose'])+'</td><td>%.8f%%</td><td>%.8f%%</td></tr>'%(100*m['before_p95_height'],100*m['after_p95_height'])
    text+='</table><p>Gate: '+e(data['status'])+'. This is eligibility for human review, not automatic promotion or proof of game compatibility. Existing unrelated review flags remain visible.</p>'
    for pose,view in views:
        stem=pose+'-'+region+'-'+view+'.png'
        text+='<h2>'+e(pose+' / '+region+' / '+view)+'</h2><p>Before</p><img src="before/renders/'+e(stem)+'"><p>After</p><img src="after/renders/'+e(stem)+'">'
    text+='<h2>Complete gate</h2><pre>'+e(json.dumps(data,indent=2))+'</pre></body></html>'
    (output/'index.html').write_text(text,encoding='utf-8')
    (output/'README.txt').write_text('Extract everything and open index.html.\nNo PAC was written. Experimental candidate.yobj is not a replacement PAC.\npreview/candidate.obj and PNG/MTL files support Noesis inspection.\nQA renders are geometry-only CPU renders. Report poses are synthetic.\nThe accepted baseline is preserved and identified by SHA-256.\n',encoding='utf-8')
    manifest={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'manifest.json').write_text(json.dumps({'sha256':manifest},indent=2)+'\n')
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(output)))
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failure')
    print(json.dumps(dict(archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),gate=data['status'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','trial','gate','baseline','output','archive','title','region'):p.add_argument('--'+name,required=True)
    p.add_argument('--view',action='append',required=True,metavar='POSE:VIEW');p.add_argument('--evidence',action='append',default=[],metavar='NAME=PATH')
    a=p.parse_args();build(a.before,a.after,a.trial,a.gate,a.baseline,a.output,a.archive,a.title,a.region,[tuple(v.split(':')) for v in a.view],[v.split('=',1) for v in a.evidence])
