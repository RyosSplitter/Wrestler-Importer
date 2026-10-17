"""Isolated JBI arm/hand trials; no production adapter registration.

The earlier ``sym_*`` trial names refer to an archive subsequently identified
by its owner as JBI. They are retained as reproducible historical controls.
"""
import copy
import re

import numpy as np

from tools.prepare_model import Surface, bone_matrices
from tools.sym_rig import arrays


def finger_chains(model, side):
    """Identify digits by label, but segment order by parent links, not suffix.

    Fail closed on missing, branched or mixed-digit chains. Digit labels still
    need anatomical confirmation on a new source family; this is not a claim
    that arbitrary same-name controllers have compatible animation semantics.
    """
    bones = model['bones']
    hands = [b['index'] for b in bones if b['name'] == side+'_te']
    if len(hands) != 1:
        raise ValueError('Expected one hand anchor')
    output = {}
    for digit in range(5):
        members = {b['index'] for b in bones
                   if re.fullmatch(side+'_yubi'+str(digit)+r'\d', b['name'])}
        roots = [i for i in members if bones[i]['parent'] == hands[0]]
        if len(roots) != 1:
            raise ValueError('Missing/ambiguous digit root')
        chain = [roots[0]]
        while True:
            children = [i for i in members if bones[i]['parent'] == chain[-1]]
            if not children:
                break
            if len(children) != 1 or children[0] in chain:
                raise ValueError('Branched/cyclic digit chain')
            chain += children
        if set(chain) != members:
            raise ValueError('Disconnected digit chain')
        output[digit] = chain
    return output


def digit_review(source, target, source_weights, weights):
    rows = []
    for side in ('l', 'r'):
        sc, tc = finger_chains(source, side), finger_chains(target, side)
        all_fingers = [b['index'] for b in target['bones'] if '_yubi' in b['name']]
        for digit, chain in sc.items():
            support = source_weights[:, chain].sum(1) > 1e-7
            foreign = [i for i in all_fingers if i not in tc[digit]]
            leak = weights[:, foreign].sum(1)
            rows.append(dict(side=side, digit=digit, records=int(support.sum()),
                wrong_digit_records=int(np.count_nonzero(support & (leak > 1e-6))),
                wrong_digit_weight_mass=float(leak[support].sum()),
                maximum_wrong_digit_mass=float(leak[support].max(initial=0))))
    return rows


def _segment_query(points, source_start, source_end, target_start, target_end):
    """Similarity warp for donor queries ONLY; never apply it to output vertices."""
    a, b = source_end-source_start, target_end-target_start
    la, lb = np.linalg.norm(a), np.linalg.norm(b)
    if min(la, lb) < 1e-7:
        raise ValueError('Degenerate arm segment')
    a, b = a/la, b/lb
    cross = np.cross(a, b); sine = np.linalg.norm(cross); cosine = np.dot(a, b)
    if cosine < -1+1e-7:
        raise ValueError('Reversed segment orientation requires explicit review')
    skew = np.array([[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]])
    rotation = np.eye(3)+skew+skew@skew/(1+cosine)
    return (points-source_start)@rotation.T*(lb/la)+target_start


def refine_arms_chain_control(source, target, baseline, alignment):
    """Preserve source anatomical support; replace only hand/arm-helper records.

    Two source finger segments use the first two PSP chain segments in
    proximal-to-distal order. The third PSP segment gets no invented source
    influence. This is a conservative trial requiring an in-game grip test.
    Arm helpers use segment-aligned donor queries restricted to the matching
    upper arm/forearm/wrist support. Their animation semantics remain inferred.
    """
    result = copy.deepcopy(baseline)
    positions, original = arrays(baseline)
    _, sw = arrays(source)
    sw /= sw.sum(1)[:, None]
    sm, tm = bone_matrices(source), bone_matrices(target)
    r = np.asarray(alignment['rotation']); t = np.asarray(alignment['translation']); scale = alignment['scale']
    source_origins = scale*sm[:, :3, 3]@r.T+t
    target_origins = tm[:, :3, 3]
    sb = {b['name']: b['index'] for b in source['bones']}
    tb = {b['name']: b['index'] for b in target['bones']}
    affected = np.zeros(len(positions), bool)
    replacement = np.zeros_like(original)
    replaced_mass = np.zeros(len(positions))
    maps, helpers = [], []
    for side in ('l', 'r'):
        sc, tc = finger_chains(source, side), finger_chains(target, side)
        for digit in range(5):
            if len(sc[digit]) != 2 or len(tc[digit]) != 3:
                raise ValueError('Untested source/target digit segment count')
            for source_index, target_index in zip(sc[digit], tc[digit]):
                mass = sw[:, source_index]
                replacement[:, target_index] += mass
                replaced_mass += mass
                maps.append(dict(source=source['bones'][source_index]['name'],
                    target=target['bones'][target_index]['name'],
                    rule='Parent-chain order, source two-segment support retained',
                    records=int(np.count_nonzero(mass > 1e-7))))
        for stem, end, allowed in (
            ('ninoude', 'kote', ('ninoude', 'ninoude_x', 'kote')),
            ('kote', 'te', ('kote', 'kote_x', 'te')),
            ('te', None, ('kote_x', 'te'))):
            indices = [b['index'] for b in source['bones']
                       if re.fullmatch(side+'_'+stem+r'_w\d\d', b['name'])]
            mass = sw[:, indices].sum(1) if indices else np.zeros(len(sw))
            selected = mass > 1e-7
            if not selected.any():
                continue
            allowed_indices = [tb[side+'_'+name] for name in allowed]
            # Only ordinary donor triangles with substantial matching support.
            donor = copy.deepcopy(target)
            for mesh in donor['meshes']:
                for mat in mesh['materials']:
                    def local_support(vi):
                        v = mesh['vertices'][vi]
                        return sum(w for b, w in zip(mesh['bone_palette'], v['weights']) if b in allowed_indices)
                    mat['triangles'] = [tri for tri in mat['triangles']
                        if mat.get('control') not in (0x115, 0x117)
                        and min(local_support(i) for i in tri) > .25]
            surface = Surface(donor)
            start = sb[side+'_'+stem]; target_start = tb[side+'_'+stem]
            if end:
                source_end = source_origins[sb[side+'_'+end]]
                target_end = target_origins[tb[side+'_'+end]]
            else:
                # Wrist query orientation/scale comes from its forearm; no
                # source digit is sampled from another PSP finger or thumb.
                source_end = 2*source_origins[start]-source_origins[sb[side+'_kote']]
                target_end = 2*target_origins[target_start]-target_origins[tb[side+'_kote']]
            queries = _segment_query(positions[selected], source_origins[start], source_end,
                                     target_origins[target_start], target_end)
            distances = []
            for row, query in zip(np.flatnonzero(selected), queries):
                index, bary, distance = surface.nearest(query)
                mesh, tri = surface.corners[index]
                w = np.zeros(target['bone_count'])
                for coefficient, vi in zip(bary, tri):
                    for bone, value in zip(mesh['bone_palette'], mesh['vertices'][vi]['weights']):
                        if bone in allowed_indices:
                            w[bone] += coefficient*value
                if w.sum() <= 1e-7:
                    raise ValueError('No compatible donor arm support')
                replacement[row] += mass[row]*w/w.sum()
                distances.append(distance)
            replaced_mass += mass
            helpers.append(dict(side=side, source_helpers=[source['bones'][i]['name'] for i in indices],
                allowed_target_support=[target['bones'][i]['name'] for i in allowed_indices],
                records=int(selected.sum()), query_distance_max=max(distances),
                query_transform_only=True, output_vertex_motion=False))
    affected = replaced_mass > 1e-7
    # Preserve direct source body coefficients; unmodified records retain the
    # complete baseline (including the separately tested ocular/jaw guard).
    from tools.sym_rig import BODY_NAMES
    direct = np.zeros_like(original)
    for b in source['bones']:
        if b['name'] in BODY_NAMES and b['name'] in tb:
            direct[:, tb[b['name']]] += sw[:, b['index']]
    # Affected records must consist solely of represented body + selected
    # hand/arm-helper mass. Never discard unrelated source influences.
    represented = direct.sum(1)+replaced_mass
    if np.any(np.abs(represented[affected]-1) > 1e-5):
        raise ValueError('Arm trial overlaps unhandled source controllers')
    new = original.copy(); new[affected] = (direct+replacement)[affected]
    if np.max(np.count_nonzero(new > 1e-7, axis=1)) > 4:
        raise ValueError('Arm trial needs influence pruning; review instead of silently pruning')
    new[affected] /= new[affected].sum(1)[:, None]
    before = digit_review(source, target, sw, original)
    after = digit_review(source, target, sw, new)
    if any(r['wrong_digit_records'] for r in after):
        raise ValueError('Foreign digit influence remains')
    row = 0
    for mesh in result['meshes']:
        for v in mesh['vertices']:
            v['weights'] = new[row, mesh['bone_palette']].tolist(); row += 1
    if not np.array_equal(arrays(result)[0], positions):
        raise ValueError('Arm refinement moved geometry')
    report = dict(status='EXPERIMENTAL; actual controller semantics require PPSSPP',
        changed_records=int(np.count_nonzero(np.max(np.abs(original-new), axis=1) > 1e-7)),
        eligible_records=int(affected.sum()), unaffected_weights_exact=bool(np.array_equal(original[~affected],new[~affected])),
        positions_exact=True, finger_mapping=maps, helper_mapping=helpers,
        digit_review_before=before, digit_review_after=after,
        maximum_weight_sum_error=float(np.max(np.abs(new.sum(1)-1))),
        maximum_influences=int(np.max(np.count_nonzero(new > 1e-7, axis=1))),
        limitation='PSP third phalanx unused for two-segment JBI digits; actual grips/twists need gameplay review')
    return result, report


def _restricted_surface(target, allowed):
    donor=copy.deepcopy(target)
    for mesh in donor['meshes']:
        def supported(vi):
            v=mesh['vertices'][vi]
            return sum(w for b,w in zip(mesh['bone_palette'],v['weights']) if b in allowed)
        for mat in mesh['materials']:
            mat['triangles']=[tri for tri in mat['triangles'] if
                mat.get('control') not in (0x115,0x117) and min(supported(i) for i in tri)>.25]
    return Surface(donor)


def rebind_arm_reference(source,target,prepared,alignment):
    """Local source-to-PSP bind conversion, not an arbitrary shape correction.

    Shoulder surface anchors are pinned to the previously accepted model.
    Upper-arm and forearm centerlines end at the actual PSP elbow/wrist; radial
    offsets are preserved. Hands preserve per-bone local offsets in matching
    PSP rest frames. The thumb's two phalanges correspond to PSP segments 1/2,
    leaving its additional metacarpal to be represented by donor skinning.
    """
    result=copy.deepcopy(prepared);p,_=arrays(prepared);_,sw=arrays(source)
    sw/=sw.sum(1)[:,None]
    sm,tm=bone_matrices(source),bone_matrices(target)
    r=np.asarray(alignment['rotation']);t=np.asarray(alignment['translation'])
    so=alignment['scale']*sm[:,:3,3]@r.T+t
    sb={b['name']:b['index'] for b in source['bones']};tb={b['name']:b['index'] for b in target['bones']}
    normals=np.array([v['normal'] for m in prepared['meshes'] for v in m['vertices']])
    q=p.copy();nn=normals.copy();affected=np.zeros(len(p),bool);rows=[]
    for side in ('l','r'):
        sc,tc=finger_chains(source,side),finger_chains(target,side)
        arm_ids=[b['index'] for b in source['bones'] if b['name'].startswith(side+'_') and
                 any(stem in b['name'] for stem in ('ninoude','kote','_te','yubi'))]
        mask=sw[:,arm_ids].sum(1)>1e-7;affected|=mask
        a,b,c=[so[sb[side+'_'+stem]] for stem in ('ninoude','kote','te')]
        x,y,z=a,tm[tb[side+'_kote'],:3,3],tm[tb[side+'_te'],:3,3]
        distances=[];maps=[];normal_maps=[]
        for start,end,newstart,newend in [(a,b,x,y),(b,c,y,z)]:
            axis=end-start;length=np.linalg.norm(axis);u=axis/length
            newaxis=newend-newstart;newlength=np.linalg.norm(newaxis);v=newaxis/newlength
            cross=np.cross(u,v);skew=np.array([[0,-cross[2],cross[1]],[cross[2],0,-cross[0]],[-cross[1],cross[0],0]])
            rot=np.eye(3)+skew+skew@skew/(1+np.dot(u,v))
            alpha=np.clip((p-start)@u/length,0,1)
            closest=start+alpha[:,None]*axis
            distances.append(np.linalg.norm(p-closest,axis=1))
            maps.append(newstart+alpha[:,None]*newaxis+(p-closest)@rot.T)
            # Inverse-transpose of axial length adaptation; no radial scaling.
            jacobian=rot@(np.eye(3)+(newlength/length-1)*np.outer(u,u))
            normal_maps.append(normals@np.linalg.inv(jacobian))
        segment=np.argmin(distances,axis=0)
        for i in (0,1):
            selected=mask & (segment==i);q[selected]=maps[i][selected];nn[selected]=normal_maps[i][selected]
        mapping={sb[side+'_te']:tb[side+'_te']}
        mapping.update({b['index']:tb[side+'_te'] for b in source['bones'] if re.fullmatch(side+r'_te_w\d\d',b['name'])})
        for digit in range(5):mapping.update(zip(sc[digit],tc[digit][1:] if digit==0 else tc[digit][:2]))
        hand_mass=sw[:,list(mapping)].sum(1);hand=hand_mass>1e-7
        if np.any(np.abs(hand_mass[hand]-1)>1e-5):raise ValueError('Blended hand bind conversion requires explicit review')
        q[hand]=0;nn[hand]=0
        for si,ti in mapping.items():
            rot=tm[ti,:3,:3]@(r@sm[si,:3,:3]).T
            transformed=(p-so[si])@rot.T+tm[ti,:3,3]
            q[hand]+=sw[hand,si,None]*transformed[hand]
            nn[hand]+=sw[hand,si,None]*(normals@rot.T)[hand]
        rows.append(dict(side=side,source_shoulder=a.tolist(),pinned_shoulder=x.tolist(),
            source_elbow=b.tolist(),target_elbow=y.tolist(),source_wrist=c.tolist(),target_wrist=z.tolist(),
            wrist_origin_mismatch=float(np.linalg.norm(c-z)),records=int(mask.sum()),
            shoulder_surface_anchor_pinned=True,radial_arm_scaling=False))
    # Coincident but independently weighted records must stay independent.
    # Detect rest cracks; never average their weights or weld their topology.
    groups={}
    for i,point in enumerate(p):groups.setdefault(tuple(point),[]).append(i)
    gaps=[float(np.max(np.linalg.norm(q[ids]-q[ids[0]],axis=1))) for ids in groups.values() if len(ids)>1]
    gap=max(gaps,default=0)
    if gap>2e-5:raise ValueError('Bind adaptation opened a coincident source seam: '+str(gap))
    row=0
    for mesh in result['meshes']:
        for vertex in mesh['vertices']:
            vertex['position']=np.asarray(q[row],np.float32).astype(float).tolist()
            vertex['normal']=(nn[row]/np.linalg.norm(nn[row])).tolist() if affected[row] else vertex['normal']
            row+=1
    return result,dict(policy='Local anatomical bind conversion: pinned shoulder surface, actual PSP elbow/wrist, matched phalanx rest frames',
        regions=rows,maximum_rest_seam_gap=gap,unaffected_positions_exact=bool(np.array_equal(p[~affected],q[~affected])),
        changed_records=int(np.count_nonzero(np.linalg.norm(q-p,axis=1)>1e-7)),
        maximum_position_change=float(np.linalg.norm(q-p,axis=1).max()),
        arbitrary_displacement=False,topology_uv_colors_materials_preserved=True)


def refine_arms(source,target,baseline,alignment):
    """Local arm/hand bind conversion, then digit-constrained surface transfer.

    Source thumb has two phalanges; PSP adds a proximal metacarpal controller.
    Palm transfer can represent that controller, unlike a rigid two-bone map.
    Surface transfer explores only this hand's anatomy. Rest geometry changes
    are limited to the separately reported anatomical bind-frame conversion.
    """
    # Retain the isolated arm-helper experiment, but replace its hand control
    # completely. The chain-only result remains reproducible as a failed control.
    result,control_report=refine_arms_chain_control(source,target,baseline,alignment)
    result,bind_report=rebind_arm_reference(source,target,result,alignment)
    positions,weights=arrays(result);_,original=arrays(baseline);_,sw=arrays(source)
    sw/=sw.sum(1)[:,None]
    sb={b['name']:b['index'] for b in source['bones']};tb={b['name']:b['index'] for b in target['bones']}
    reports=[]
    # Once the reference pose has been adapted, query in the actual resulting
    # bind coordinates. Include the parent-side controller at joint transitions;
    # excluding the clavicle wrongly makes the shoulder cap follow the arm 100%.
    from tools.sym_rig import BODY_NAMES
    direct=np.zeros_like(weights);arm_replacement=np.zeros_like(weights);arm_mass=np.zeros(len(weights))
    for bone in source['bones']:
        if bone['name'] in BODY_NAMES and bone['name'] in tb:
            direct[:,tb[bone['name']]]+=sw[:,bone['index']]
    helpers=[]
    for side in ('l','r'):
        for stem,allowed in [('ninoude',('sakotsu','ninoude','ninoude_x','kote')),
                             ('kote',('ninoude_x','kote','kote_x','te'))]:
            ids=[b['index'] for b in source['bones'] if re.fullmatch(side+'_'+stem+r'_w\d\d',b['name'])]
            mass=sw[:,ids].sum(1) if ids else np.zeros(len(weights));mask=mass>1e-7
            if not mask.any():continue
            allowed_indices=[tb[side+'_'+part] for part in allowed]
            surface=_restricted_surface(target,allowed_indices);distances=[]
            for row in np.flatnonzero(mask):
                index,bary,distance=surface.nearest(positions[row]);mesh,tri=surface.corners[index]
                w=np.zeros(target['bone_count'])
                for coefficient,vi in zip(bary,tri):
                    for bone,value in zip(mesh['bone_palette'],mesh['vertices'][vi]['weights']):
                        if bone in allowed_indices:w[bone]+=coefficient*value
                arm_replacement[row]+=mass[row]*w/w.sum();distances.append(distance)
            arm_mass+=mass
            helpers.append(dict(side=side,source_helpers=[source['bones'][i]['name'] for i in ids],
                allowed_target_support=[target['bones'][i]['name'] for i in allowed_indices],
                records=int(mask.sum()),maximum_query_distance=max(distances),query_frame='Actual PSP bind geometry'))
    mask=arm_mass>1e-7
    if np.any(np.abs((direct.sum(1)+arm_mass)[mask]-1)>1e-5):
        raise ValueError('Arm helper overlaps unhandled controller')
    weights[mask]=(direct+arm_replacement)[mask]
    for side in ('l','r'):
        sc,tc=finger_chains(source,side),finger_chains(target,side)
        source_hand=[sb[side+'_te']]+[b['index'] for b in source['bones'] if re.fullmatch(side+r'_te_w\d\d',b['name'])]
        all_source_fingers=[i for chain in sc.values() for i in chain]
        all_target_fingers=[i for chain in tc.values() for i in chain]
        hand_mass=sw[:,source_hand+all_source_fingers].sum(1)
        selected=hand_mass>1e-7
        # Remove exactly the hand component produced by the chain control.
        # Source records blending wrist-helper and other arm mass need separate
        # decomposition; reject rather than accidentally removing other mass.
        if np.any(np.abs(hand_mass[selected]-1)>1e-5):
            raise ValueError('Blended source hand/arm boundary needs explicit decomposition')
        finger_support=[sw[:,sc[d]].sum(1)>1e-7 for d in range(5)]
        if np.max(np.sum(finger_support,axis=0))>1:
            raise ValueError('Overlapping source digits need explicit correspondence')
        # The converted hand is now in native bind coordinates. Preserve known
        # digit identity while allowing the palm to acquire the extra native
        # metacarpal support absent from the two-phalange source thumb.
        palm=selected & ~np.any(finger_support,axis=0)
        for digit in [None,*range(5)]:
            mask=palm if digit is None else selected & finger_support[digit]
            if not mask.any():continue
            allowed=[tb[side+'_te'],tb[side+'_kote_x'],*(all_target_fingers if digit is None else tc[digit])]
            surface=_restricted_surface(target,allowed)
            queries=positions[mask]
            distances=[]
            for row,query in zip(np.flatnonzero(mask),queries):
                index,bary,distance=surface.nearest(query);mesh,tri=surface.corners[index]
                w=np.zeros(target['bone_count'])
                for coefficient,vi in zip(bary,tri):
                    for bone,value in zip(mesh['bone_palette'],mesh['vertices'][vi]['weights']):
                        if bone in allowed:w[bone]+=coefficient*value
                if w.sum()<1e-7:raise ValueError('No compatible hand surface support')
                weights[row]=w/w.sum();distances.append(distance)
            reports.append(dict(side=side,region='palm' if digit is None else 'digit-'+str(digit),
                records=int(mask.sum()),allowed_target_support=[target['bones'][i]['name'] for i in allowed],
                query_frame='Actual converted PSP bind coordinates',
                maximum_query_distance=max(distances),output_geometry_changed=True))
    if np.max(np.count_nonzero(weights>1e-7,axis=1))>4:
        raise ValueError('Hand transfer exceeds four influences; review required')
    review=digit_review(source,target,sw,weights)
    if any(r['wrong_digit_records'] for r in review):raise ValueError('Wrong-digit influence after constrained transfer')
    row=0
    for mesh in result['meshes']:
        for v in mesh['vertices']:v['weights']=weights[row,mesh['bone_palette']].tolist();row+=1
    report=dict(status='EXPERIMENTAL; PPSSPP review required',hand_transfer=reports,digit_review_after=review,
        digit_review_before=digit_review(source,target,sw,original),
        positions_exact=False,bind_reference_conversion=bind_report,
        helper_mapping=helpers,
        changed_records=int(np.count_nonzero(np.max(np.abs(original-weights),axis=1)>1e-7)),
        maximum_influences=int(np.max(np.count_nonzero(weights>1e-7,axis=1))),
        maximum_weight_sum_error=float(np.max(np.abs(weights.sum(1)-1))),
        hand_policy='Local bind conversion followed by anatomical digit-constrained donor transfer; thumb metacarpal represented through palm transfer',
        failed_control='refine_arms_chain_control: two-to-three chain mapping alone stretches the thumb web',
        limitation='Real animation semantics, grips, twists and pad states require PPSSPP; localized anatomical bind conversion is experimental')
    return result,report
