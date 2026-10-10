"""Bundled Blender entry point; wraps the established reducer without changing it.

Freeze source triangles in torso/pelvis, ocular and material-boundary regions.
Other faces retain their established regional floors without budget redistribution.
The selections are geometric/weight evidence, never wrestler/file-name patches.
"""
import copy
from collections import Counter,defaultdict
import json
import re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import region_mesh


def select_guards(model):
    bone_regions=region_mesh.bone_regions(model['bones'])
    eye_bones={b['index'] for b in model['bones'] if b['name'] in ('l_eye','r_eye','l_mabuta','r_mabuta')}
    edges=defaultdict(set)
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                ps=[tuple(mesh['vertices'][i]['position']) for i in tri]
                for a,b in zip(ps,ps[1:]+ps[:1]):edges[tuple(sorted((a,b)))].add(mat['texture_id'])
    boundary={p for edge,mats in edges.items() if len(mats)>1 for p in edge}
    decisions=[]
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            for ti,tri in enumerate(mat['triangles']):
                vertices=[mesh['vertices'][i] for i in tri]
                torso=sum(sum(w for b,w in zip(mesh['bone_palette'],v['weights']) if bone_regions[b]=='Torso') for v in vertices)/3
                eyes=any(any(w>1e-7 and b in eye_bones for b,w in zip(mesh['bone_palette'],v['weights'])) for v in vertices)
                seam=any(tuple(v['position']) in boundary for v in vertices)
                cutout=mat['texture_id'] in model.get('cutout_texture_ids',[])
                decisions.append((mesh['index'],mat['texture_id'],ti,torso>.5 or eyes or seam or cutout))
    return decisions


def run(source_path,output_path,profile_path):
    import blender_reduce
    model=json.loads(Path(source_path).read_text());profile=json.loads(Path(profile_path).read_text())
    if Path(output_path).exists():raise FileExistsError(output_path)
    region_mesh.RATIOS.update(profile['ratios']);blender_reduce.RATIOS.update(profile['ratios'])
    selections={(mi,tid,ti):held for mi,tid,ti,held in select_guards(model)}
    free=copy.deepcopy(model);held=copy.deepcopy(model)
    for dst,keep in ((free,False),(held,True)):
        for mesh in dst['meshes']:
            mats=[]
            for mat in mesh['materials']:
                mat['triangles']=[t for i,t in enumerate(mat['triangles']) if selections[mesh['index'],mat['texture_id'],i]==keep]
                if mat['triangles']:mats.append(mat)
            mesh['materials']=mats
        dst['meshes']=[m for m in dst['meshes'] if m['materials']]
        dst['triangle_count']=sum(len(a['triangles']) for m in dst['meshes'] for a in m['materials'])
    regions=region_mesh.make_regions(free)
    for mesh in held['meshes']:
        # Source preparation uses a dense target palette; preserved copies keep
        # only referenced records so unused vertices do not affect owner locks.
        used=sorted({i for a in mesh['materials'] for t in a['triangles'] for i in t})
        remap={old:new for new,old in enumerate(used)}
        mesh['vertices']=[mesh['vertices'][i] for i in used]
        for mat in mesh['materials']:mat['triangles']=[[remap[i] for i in t] for t in mat['triangles']]
        for v in mesh['vertices']:v['smoothing_group']=0
        mesh.update(index=len(regions['meshes']),region='Preserved')
        regions['meshes'].append(mesh)
    regions['triangle_count']=model['triangle_count']
    # Corner remapping can drop a degenerate output triangle after Blender's
    # modifier count. Increase that region's requested retention and retry;
    # never waive the established floor or change unrelated region ratios.
    retries=[];reserve={}
    for attempt in range(5):
        try:
            result=blender_reduce.reduce(regions,1.,regional=True,preserved_regions=('Preserved',),retention_reserve=reserve);break
        except ValueError as exc:
            match=re.fullmatch(r'(Head|Torso|Arms|Legs): retained (\d+)/(\d+) faces, below requested minimum',str(exc))
            if not match or attempt==4:raise
            import math
            region=match[1];missing=math.ceil(int(match[3])*profile['ratios'][region])-int(match[2])
            reserve[region]=reserve.get(region,0)+max(2,missing);retries.append(dict(region=region,extra_modifier_faces=reserve[region]))
    result['reduction_report']['retention_floor_retries']=retries
    # Blender's corner exporter rounds UVs to six decimals. At an unchanged
    # protected position this can create two otherwise identical corner records
    # on either side of a held/free boundary. Restore a uniquely matching original
    # material UV; never weld different UV islands or move a geometric point.
    uv_reference=defaultdict(set)
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            for i in {i for t in mat['triangles'] for i in t}:
                v=mesh['vertices'][i];uv_reference[tuple(v['position']),mat['texture_id']].add(tuple(v['uv']))
    restored=0
    for mesh in result['meshes']:
        uses=defaultdict(set)
        for mat in mesh['materials']:
            for i in {i for t in mat['triangles'] for i in t}:uses[i].add(mat['texture_id'])
        for i,v in enumerate(mesh['vertices']):
            candidates=set()
            for tid in uses[i]:
                candidates.update(uv for uv in uv_reference[tuple(v['position']),tid] if max(abs(a-b) for a,b in zip(uv,v['uv']))<=1e-6)
            if len(candidates)==1:
                original_uv=next(iter(candidates))
                if tuple(v['uv'])!=original_uv:v['uv']=list(original_uv);restored+=1
    result['reduction_report']['exact_original_uv_records_restored']=restored
    result['reduction_report']['guard_policy']='Source torso/pelvis, eye-controller support, cutouts and all shared material-boundary rings; no budget redistribution'
    result['reduction_report']['protected_triangles']=held['triangle_count']
    Path(output_path).write_text(json.dumps(result,allow_nan=False))


if __name__=='__main__':
    run(*sys.argv[sys.argv.index('--')+1:])
