"""Isolated SYM rig experiments, not verified animation conversion rules."""
import copy
import struct

import numpy as np

from model_qa.geometry import align_reference
from tools.prepare_model import bone_matrices
from tools.weight_trial_review import map_source, transfer


# Matching names in these body chains are a testable hypothesis. Controllers,
# fingers and SYM _w helpers are deliberately excluded, even if names match.
BODY_NAMES = {'root', 'koshi', 'mune', 'kubi'} | {
    side+'_'+part for side in ('l', 'r') for part in
    ('sakotsu', 'ninoude', 'kote', 'te', 'momo', 'sune', 'ashi', 'tsumasaki')}


def arrays(model):
    positions = np.array([v['position'] for m in model['meshes'] for v in m['vertices']])
    weights = np.zeros((len(positions), model['bone_count']))
    for i, (mesh, vertex) in enumerate((m, v) for m in model['meshes'] for v in m['vertices']):
        weights[i, mesh['bone_palette']] = vertex['weights']
    return positions, weights


def bounds_probe(raw, model):
    """Test the +64 float4 as an influence sphere; do not rename old API fields."""
    start = struct.unpack_from('<I', raw, 40)[0]+8
    positions, weights = arrays(model)
    matrices = bone_matrices(model)
    rows = []
    for bone in model['bones']:
        center_radius = struct.unpack_from('<4f', raw, start+bone['index']*80+64)
        center, radius = np.array(center_radius[:3]), center_radius[3]
        affected = positions[weights[:, bone['index']] > 1e-7]
        maximum = float(np.max(np.linalg.norm(affected-center, axis=1))) if len(affected) else 0.
        rows.append(dict(name=bone['name'], active_records=len(affected),
            stored_center=center.tolist(), stored_radius=radius,
            local_chain_origin=matrices[bone['index'], :3, 3].tolist(),
            center_to_chain_origin=float(np.linalg.norm(center-matrices[bone['index'], :3, 3])),
            maximum_affected_distance=maximum,
            enclosed_at_1e_minus_4=bool(maximum <= radius+1e-4)))
    active = [r for r in rows if r['active_records']]
    return dict(bones=rows, active_bones=len(active),
        enclosing_active_bones=sum(r['enclosed_at_1e_minus_4'] for r in active),
        maximum_center_origin_distance=max(r['center_to_chain_origin'] for r in rows),
        interpretation='INFERRED influence bounds, not demonstrated joint origins; game culling use UNKNOWN')


def guard_ocular_support(source,target,sw,weights):
    """Experimental rigid-eyeball role mapping; exclude donor eye spill.

    Source support identifies actual geometry roles, not controller animation
    semantics. Only rigid, nonoverlapping source eye support is handled here.
    Surrounding skin keeps donor lids/brows/jaw; leaked eyeball mass moves to the
    PSP head anchor. No vertex is moved and no jaw coefficient may change.
    """
    sb={b['name']:b['index'] for b in source['bones']}
    tb={b['name']:b['index'] for b in target['bones']}
    result=weights.copy();source_support=[];leaks=[]
    for side in ('l','r'):
        name=side+'_eye'
        supported=sw[:,sb[name]]>1e-7 if name in sb else np.zeros(len(sw),bool)
        source_support.append(supported)
        if name not in tb:continue
        leaked=(~supported)&(result[:,tb[name]]>0)
        if leaked.any():
            if 'atama' not in tb:raise ValueError('No PSP head anchor for ocular support guard')
            result[leaked,tb['atama']]+=result[leaked,tb[name]]
            result[leaked,tb[name]]=0
        leaks.append(dict(controller=name,donor_spill_records=int(leaked.sum())))
    if np.any(source_support[0]&source_support[1]):
        raise ValueError('Overlapping source eye support is outside this rigid-eyeball experiment')
    jaw=[b['index'] for b in target['bones'] if b['name']=='d_kuchi' or b['name'].startswith('d_kuchi_')]
    for side,supported in zip(('l','r'),source_support):
        name=side+'_eye'
        if not supported.any():continue
        if name not in tb or np.any(np.abs(sw[supported,sb[name]]-1)>1e-5):
            raise ValueError('Source eye support is not compatible with the tested rigid-eyeball rule')
        if jaw and np.any(result[supported][:,jaw]>1e-7):
            raise ValueError('Source eyeball support overlaps transferred jaw controllers; review required')
        result[supported]=0
        result[supported,tb[name]]=1
    if jaw and not np.array_equal(weights[:,jaw],result[:,jaw]):
        raise ValueError('Ocular guard changed jaw coefficients')
    return result,dict(policy='Rigid source eyeball support uses corresponding native role; donor eye spill attaches to atama; donor lids/brows/jaw retained',
        source_eye_records=sum(int(s.sum()) for s in source_support),donor_spill=leaks,
        changed_records=int(np.count_nonzero(np.max(np.abs(result-weights),axis=1)>1e-7)),
        jaw_coefficients_exact=True,source_geometry_changed=False,
        limitation='Rigid eye role/motion hypothesis; source/PSP animation semantics still require PPSSPP')


def prepare_trial(source, target, *, method='conservative-hybrid',ocular_support_guard=True):
    if method not in ('conservative-hybrid', 'ancestor-control'):
        raise ValueError('Unknown SYM weighting experiment')
    aligned, fit = align_reference(source, target)
    positions, sw = arrays(aligned)
    sums = sw.sum(1)
    if np.any(sums <= 0) or np.max(np.abs(sums-1)) > 1e-5:
        raise ValueError('Invalid source skinning sums')
    sw = sw/sums[:, None]
    names = {b['name']: b['index'] for b in target['bones']}
    retained = np.zeros((len(positions), target['bone_count']))
    donor_report = None
    if method == 'ancestor-control':
        weights, missing, redirects = map_source(source, target, sw, True)
        if missing.max() > 1e-7:
            raise ValueError('Ancestor control has unmapped source mass')
        unrepresented = np.zeros(len(positions))
    else:
        redirects = {}
        for bone in source['bones']:
            if bone['name'] in BODY_NAMES and bone['name'] in names:
                retained[:, names[bone['name']]] += sw[:, bone['index']]
        unrepresented = np.maximum(1-retained.sum(1), 0)
        donor, donor_report = transfer(target, positions)
        weights = retained+unrepresented[:, None]*donor
    ocular_report=None
    if method=='conservative-hybrid' and ocular_support_guard:
        weights,ocular_report=guard_ocular_support(source,target,sw,weights)
    before = weights.copy()
    np.put_along_axis(weights, np.argsort(weights, axis=1)[:, :-4], 0, axis=1)
    removed = before.sum(1)-weights.sum(1)
    weights /= weights.sum(1)[:, None]
    if not np.isfinite(weights).all() or weights.min() < 0:
        raise ValueError('Invalid mapped weights')
    row = 0
    for mesh in aligned['meshes']:
        mesh['bone_palette'] = list(range(target['bone_count']))
        for vertex in mesh['vertices']:
            vertex['weights'] = weights[row].tolist()
            vertex['position'] = np.asarray(vertex['position'], np.float32).astype(float).tolist()
            normal = np.array(vertex['normal'])
            if np.linalg.norm(normal) < 1e-12:
                raise ValueError('Unusable source normal')
            vertex['normal'] = (normal/np.linalg.norm(normal)).tolist()
            row += 1
    aligned.update(bones=copy.deepcopy(target['bones']), bone_count=target['bone_count'],
        model_name=target['model_name'], uv_v_flipped=False, weight_encoding='float')
    report = dict(method=method, alignment=fit, direct_body_name_hypothesis=sorted(BODY_NAMES),
        donor_transfer=donor_report, donor_affected_records=int(np.count_nonzero(unrepresented > 1e-7)),
        unrepresented_source_mass_mean=float(unrepresented.mean()),
        ancestor_redirects=redirects, maximum_four_influence_pruned_mass=float(removed.max()),
        ocular_support_guard=ocular_report,
        source_weight_sum_roundoff_max=float(np.max(np.abs(sums-1))),
        weight_sum_error=float(np.max(np.abs(weights.sum(1)-1))),
        original_source_records_retained=True, source_vertices_repositioned=False,
        animation_semantics='UNKNOWN; analytic probes and PPSSPP required; not a production policy')
    aligned['preparation_report'] = report
    return aligned, report
