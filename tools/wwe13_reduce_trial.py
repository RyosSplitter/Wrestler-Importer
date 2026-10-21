"""Blender-only HD-source reduction experiment using the established reducer.

Separate from production workers. Source domain/weight identity, UV loops,
boundary locks and normal recomputation are inherited, not reimplemented.
"""
import copy
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import region_mesh
from vertex_identity import annotate


def classify(model, hand_weighted=False, preserve_hand_transitions=False):
    model = annotate(copy.deepcopy(model))
    regions = region_mesh.bone_regions(model['bones'])
    names = {b['name']: b['index'] for b in model['bones']}
    hands = {b['index'] for b in model['bones'] if '_yubi' in b['name'] or b['name'] in ('l_te', 'r_te')}
    eyes = {names[n] for n in ('l_eye', 'r_eye')}
    mouth = {b['index'] for b in model['bones'] if 'kuchi' in b['name']}
    groups = {}
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                weights = [sum(mesh['vertices'][i]['weights'][j] for i in tri) / 3 for j in range(model['bone_count'])]
                if any(mesh['vertices'][i].get('skin_locked') for i in tri):
                    label = 'Preserved'
                elif mesh['role'] in ('Hair','Cutout'):
                    # Historical profile label: retain all cutout geometry,
                    # including leg decals, rather than assuming it is hair.
                    label = 'Hair'
                elif mesh['role'] in ('EyeShell', 'Eyeball') or sum(weights[j] for j in eyes) > .98:
                    label = 'Eyes'
                elif sum(weights[j] for j in mouth) > .98:
                    label = 'Mouth'
                elif sum(weights[j] for j in hands) > (1e-7 if preserve_hand_transitions else .8):
                    label = 'Hands'
                else:
                    scores = {r: sum(w for j, w in enumerate(weights) if regions[j] == r) for r in ('Head', 'Torso', 'Arms', 'Legs')}
                    label = max(scores, key=scores.get)
                if label not in groups:
                    groups[label] = dict(vertices=[], materials=defaultdict(list), lookup={})
                g = groups[label]; face = []
                for i in tri:
                    key = mesh['index'], i
                    if key not in g['lookup']:
                        v = copy.deepcopy(mesh['vertices'][i]); v['region_strength'] = 1.
                        if hand_weighted and label == 'Hands':
                            # Single-bone phalange surfaces can collapse cheaply;
                            # mixed joint/web support receives stronger retention.
                            concentration = sum(w*w for w in v['weights'])
                            v['region_strength'] = .01 + .99 * concentration**8
                        g['lookup'][key] = len(g['vertices']); g['vertices'].append(v)
                    face.append(g['lookup'][key])
                g['materials'][mat['texture_id']].append(face)
    out = copy.deepcopy(model); out['meshes'] = []
    for label, g in sorted(groups.items()):
        out['meshes'].append(dict(index=len(out['meshes']), region=label,
            bone_palette=list(range(model['bone_count'])), vertices=g['vertices'],
            materials=[dict(texture_id=tid, triangles=ts) for tid, ts in sorted(g['materials'].items())]))
    return out


def split_uv_regions(model, components=True):
    """Keep material/UV-index-connected regions separate during collapse.

    The reducer's existing shared-position guard then locks their boundaries.
    This is opt-in for the Wii experiment; legacy trial behavior is unchanged.
    """
    out=copy.deepcopy(model);out['meshes']=[]
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            parent=list(range(len(mesh['vertices'])))
            def root(i):
                while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
                return i
            for tri in mat['triangles']:
                for i in tri[1:]:a,b=root(tri[0]),root(i);parent[max(a,b)]=min(a,b)
            groups=defaultdict(list)
            for tri in mat['triangles']:groups[root(tri[0]) if components else 0].append(tri)
            for faces in groups.values():
                used=sorted({i for t in faces for i in t});lookup={old:i for i,old in enumerate(used)}
                out['meshes'].append(dict(mesh,index=len(out['meshes']),vertices=[copy.deepcopy(mesh['vertices'][i])for i in used],
                    materials=[dict(mat,triangles=[[lookup[i]for i in t]for t in faces])]))
    return out


def run(source, output, profile, hand_weighted=False, uv_islands=False, material_only=False, export_face_floor=False, opposed_normals=False, source_normals=False, preserve_uv_seams=False, preserve_hand_transitions=False):
    import blender_reduce
    source, output, profile = map(Path, (source, output, profile))
    if output.exists():
        raise FileExistsError(output)
    model = json.loads(source.read_text()); ratios = json.loads(profile.read_text())
    if opposed_normals:
        from tools.wwe13_normal_seams import mark_opposed
        model=mark_opposed(model)
    regions = classify(model, hand_weighted=hand_weighted, preserve_hand_transitions=preserve_hand_transitions)
    if uv_islands or material_only:regions=split_uv_regions(regions,components=not material_only)
    region_mesh.RATIOS.update(ratios); blender_reduce.RATIOS.update(ratios)
    result = blender_reduce.reduce(regions, 1., regional=True, preserved_regions=('Preserved',),export_face_floor=export_face_floor,source_normals=source_normals,preserve_uv_seams=preserve_uv_seams)
    result['reduction_report']['source_uv_seam_locks']=preserve_uv_seams
    result['reduction_report']['source_hand_transition_support']=dict(enabled=preserve_hand_transitions,
        policy='Any active source PSP hand/finger support belongs to the hand retention region; no influence values or positions are edited by classification')
    result['reduction_report']['export_face_floor']=export_face_floor
    if opposed_normals:result['reduction_report']['opposed_normal_protection']=model['opposed_normal_protection']
    result['reduction_report']['trial_policy'] = 'HD source experimental regional floors; not HCTP production settings'
    result['reduction_report']['hand_deformation_retention'] = dict(enabled=hand_weighted,
        collapse_strength='.01 + .99 * (sum squared source PSP influences)^8; region face floors unchanged')
    output.write_text(json.dumps(result, allow_nan=False))
    print(json.dumps(result['reduction_report'], indent=2), flush=True)


if __name__ == '__main__':
    args=sys.argv[sys.argv.index('--') + 1:]
    run(*args[:3],hand_weighted='--hand-weighted' in args[3:],uv_islands='--uv-islands' in args[3:],material_only='--material-boundaries' in args[3:],export_face_floor='--export-face-floor' in args[3:],opposed_normals='--opposed-normals' in args[3:],source_normals='--source-normals' in args[3:],preserve_uv_seams='--preserve-uv-seams' in args[3:],preserve_hand_transitions='--preserve-hand-transitions' in args[3:])
