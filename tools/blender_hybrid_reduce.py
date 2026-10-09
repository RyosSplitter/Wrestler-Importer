"""Blender worker: preserve selected source surfaces, simplify the remainder."""
from collections import Counter
import copy
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import blender_reduce
import region_mesh


def run(source_path,output_path,profile_path):
    if output_path.exists():raise FileExistsError(output_path)
    source=json.loads(source_path.read_text());profile=json.loads(profile_path.read_text())
    region_mesh.RATIOS.update(profile['ratios']);blender_reduce.RATIOS.update(profile['ratios'])
    full=region_mesh.make_regions(source);protected=set(profile['protected_textures']);free=copy.deepcopy(source)
    totals=Counter();held=Counter()
    for m in full['meshes']:
        for mat in m['materials']:
            n=len(mat['triangles']);totals[m['region']]+=n
            if source['textures'][mat['texture_id']] in protected:held[m['region']]+=n
    for m in free['meshes']:m['materials']=[a for a in m['materials'] if source['textures'][a['texture_id']] not in protected]
    free['triangle_count']=sum(len(a['triangles']) for m in free['meshes'] for a in m['materials'])
    regions=region_mesh.make_regions(free)
    free_ratios={}
    for region,total in totals.items():
        count=total-held[region]
        if count:free_ratios[region]=max(1/count,min(1.,(math.ceil(total*profile['ratios'][region])-held[region])/count))
    # Preserved meshes participate in the ownership map so free mesh borders
    # are locked, but are never passed through a modifier or geometry welding.
    for m in source['meshes']:
        mats=[];vertices=[];cache={}
        for a in m['materials']:
            tid=a['texture_id'];name=source['textures'][tid]
            if name not in protected:continue
            smoothing=0 if name in profile['smooth_protected_textures'] else tid+1
            faces=[]
            for tri in a['triangles']:
                face=[]
                for vi in tri:
                    key=(vi,smoothing)
                    if key not in cache:
                        v=copy.deepcopy(m['vertices'][vi]);v['smoothing_group']=smoothing;cache[key]=len(vertices);vertices.append(v)
                    face.append(cache[key])
                faces.append(face)
            mats.append(dict(texture_id=tid,triangles=faces))
        if mats:regions['meshes'].append(dict(index=len(regions['meshes']),region='Preserved',vertices=vertices,materials=mats,bone_palette=list(range(source['bone_count']))))
    regions['triangle_count']=source['triangle_count'];region_mesh.RATIOS.update(free_ratios);blender_reduce.RATIOS.update(free_ratios)
    result=blender_reduce.reduce(regions,1.,regional=True,preserved_regions=('Preserved',))
    actual=Counter();preserved_by_region=dict(held)
    for m in result['meshes']:
        if m['region']!='Preserved':actual[m['region']]+=sum(len(a['triangles']) for a in m['materials'])
    for region,total in totals.items():
        if actual[region]+held[region]<math.ceil(total*profile['ratios'][region]):raise ValueError('Overall region retention floor violated')
    result['reduction_report'].update(overall_region_ratios=profile['ratios'],free_region_ratios=free_ratios,
        original_region_triangles=dict(totals),protected_region_triangles=preserved_by_region,
        final_region_triangles={r:actual[r]+held[r] for r in totals},protected_source_materials=sorted(protected))
    output_path.write_text(json.dumps(result,allow_nan=False));print(json.dumps(result['reduction_report'],indent=2))


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:];run(*map(Path,args))
