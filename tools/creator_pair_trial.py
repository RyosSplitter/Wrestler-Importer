"""Reproducible private 16-combination study. Never bundles game-derived assets.

python -m tools.creator_pair_trial --first Kenny.pac --second Brian.pac --output NEW_FOLDER
"""
import argparse
from itertools import product
from pathlib import Path

from PIL import Image, ImageDraw

from model_creator.core import PARTS, build, create_project, dump, load_source, preview


def run(first,second,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Use a new study directory.')
    output.mkdir(parents=True);project=create_project(first,second,output/'project');summary=[]
    sheet=Image.new('RGB',(4*256,4*280),'#eeeeee');draw=ImageDraw.Draw(sheet)
    for number,combo in enumerate(product((0,1),repeat=4)):
        code=''.join(map(str,combo));selections=dict(zip(PARTS,combo));folder=output/code
        try:
            report=build(project,selections,folder,resolution=384)
            s=load_source(folder/'created-model.pac');m=s['model'];t={n:s['textures'][n.casefold()] for n in m['texture_names']}
            for pose in ('standing','crouch','jaw','eyes'):
                preview(m,t,'front-left',384,pose).save(folder/'preview'/('pose-'+pose+'.png'))
            row=dict(combination=code,selections=selections,passed=True,pac_bytes=report['pac_bytes'],
                     sha256=report['pac_sha256'],meshes=m['report']['meshes'],vertices=m['report']['vertices'],triangles=m['report']['triangles'],
                     texture_count=len(m['texture_names']),textures_byte_exact=report['textures_byte_exact'],
                     pose_count=len(report['qa']['poses']),review_findings=report['review_findings'],
                     maximum_interior_pose_delta=max((p['maximum_source_position_difference'] for p in report.get('interior_pose_comparison',{}).values()),default=0.))
            with Image.open(folder/'preview/front.png') as image:sheet.paste(image.resize((256,256)),((number%4)*256,(number//4)*280))
        except ValueError as exc:
            if 'exceeding' not in str(exc):raise
            row=dict(combination=code,selections=selections,passed=False,export_withheld=True,reason=str(exc))
        summary.append(row);print(code,row.get('pac_bytes',row.get('reason')),flush=True)
        draw.text(((number%4)*256+6,(number//4)*280+260),code+' | '+(str(row['pac_bytes'])+' bytes' if row['passed'] else 'Export withheld'),fill='black')
    sheet.save(output/'combinations.png');dump(output/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--first',required=True,type=Path);parser.add_argument('--second',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();run(args.first,args.second,args.output)
