"""Reproduce texture-only A/B trials on an existing converted PSP PAC."""
import argparse
from pathlib import Path
import shutil

from app.ps2_textures import read_source
from desktop.accessories import combined_preview
from desktop.preview import save_views
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections,write_preview
from tools.pac_inspect import parse_textures
from .pac import optimize_pac
from .candidates import read_gim


def previews(data,folder):
    from PIL import Image
    folder.mkdir(parents=True,exist_ok=True)
    parts={s['id']:r for s,r in sections(data)}
    models={i:audit_yobj(r) for i,r in parts.items() if r.startswith(b'YOBJ')}
    visual=combined_preview(models[2],[models[i] for i in sorted(models) if i!=2])
    table=parts[9];gims={t['name']:table[t['offset']:t['offset']+t['size']] for t in parse_textures(table)}
    write_preview(visual,folder/'output.obj');mtl=[]
    for i,n in enumerate(visual['texture_names']):
        p,c=read_gim(gims[n]);Image.fromarray(c[p]).save(folder/(n+'.png'))
        (folder/(n+'.gim')).write_bytes(gims[n]);mtl.extend(['newmtl texture_%d'%i,'Kd 1 1 1','map_Kd '+n+'.png'])
    (folder/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    for i,r in models.items():(folder/('section-%d.yobj'%i)).write_bytes(parts[i])
    save_views(visual,gims,folder,resolution=1024,gim_reader=read_gim)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--target',type=int,default=148000)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    original=a.baseline.read_bytes();names=audit_yobj(next(r for s,r in sections(original) if s['id']==2))['texture_names']
    decoded=read_source(a.source,texture_names=names)
    data,report=optimize_pac(original,decoded,a.output/'textures',target=a.target,progress=lambda m:print(m,flush=True))
    (a.output/'current.pac').write_bytes(original);(a.output/'adaptive-experimental.pac').write_bytes(data)
    previews(original,a.output/'current-preview');previews(data,a.output/'adaptive-preview')
    from PIL import Image,ImageDraw
    for view in ('front-left','front','back','left','right'):
        images=[Image.open(a.output/folder/(view+'-full.png')) for folder in ('current-preview','adaptive-preview')]
        panel=Image.new('RGB',(2048,1054),(30,30,30));draw=ImageDraw.Draw(panel)
        for i,(label,image) in enumerate(zip(('Current Texture Method','Adaptive Texture Optimization'),images)):
            panel.paste(image,(i*1024,30));draw.text((i*1024+10,8),label,fill='white')
        panel.save(a.output/(view+'-comparison.png'))
    print('Final PAC: %d bytes; baseline: %d; report: %s'%(len(data),len(original),a.output/'textures/report.html'))


if __name__=='__main__':main()
