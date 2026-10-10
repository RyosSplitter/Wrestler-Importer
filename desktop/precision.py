"""Isolated, bounded attribute-precision experiment for oversized candidates.

The PSP vertex layout remains float32. This changes stored attribute precision,
not topology, weight precision, textures, skeleton or archive construction.
It is lossy and must be reported and independently validated before export.
"""
import copy
import math

import numpy as np

from model_qa.ocular import OCULAR_NAMES

POSITION_ERROR_LIMIT = 3e-5  # fraction of complete model height
NORMAL_ANGLE_LIMIT = .25  # degrees
NORMAL_LENGTH_ERROR_LIMIT = .007
UV_ERROR_LIMIT = 1 / 32768


def ocular_positions(source_weight_control):
    ids = {b['index'] for b in source_weight_control['bones'] if b['name'] in OCULAR_NAMES}
    return {tuple(v['position']) for m in source_weight_control['meshes'] for v in m['vertices']
            if sum(w for b,w in zip(m['bone_palette'],v['weights']) if b in ids)>1e-7}


def bounded_precision(model, held_positions, divisions=65536):
    if divisions not in (65536, 32768):
        raise ValueError('Unsupported position precision trial')
    original = [v for m in model['meshes'] for v in m['vertices']]
    height = float(np.ptp([v['position'][1] for v in original]))
    if not np.isfinite(height) or height<=0:
        raise ValueError('Position precision requires a finite model height')
    step = 2.**math.floor(math.log2(height/divisions))
    result = copy.deepcopy(model)
    changed = dict(position=0, uv=0, normal=0)
    held = 0
    maximum_position = maximum_uv = maximum_angle = maximum_length = 0.
    for before,after in zip(original, [v for m in result['meshes'] for v in m['vertices']]):
        if tuple(before['position']) in held_positions:
            held += 1
            continue
        for name,quantum in (('position',step), ('uv',1/16384), ('normal',1/256)):
            old = np.asarray(before[name], dtype=np.float32).astype(float)
            new = (np.rint(old/quantum)*quantum).astype(np.float32).astype(float)
            after[name] = new.tolist()
            changed[name] += int(not np.array_equal(new,old))
            if name=='position':
                maximum_position = max(maximum_position,float(np.linalg.norm(new-old)/height))
            elif name=='uv':
                maximum_uv = max(maximum_uv,float(np.max(np.abs(new-old))))
            else:
                a,b = np.linalg.norm(old),np.linalg.norm(new)
                if min(a,b)<=1e-12:
                    raise ValueError('Precision trial encountered a zero normal')
                angle = float(np.degrees(np.arccos(np.clip(np.dot(old,new)/(a*b),-1,1))))
                maximum_angle = max(maximum_angle,angle)
                maximum_length = max(maximum_length,abs(a-b))
    if (maximum_position>POSITION_ERROR_LIMIT or maximum_uv>UV_ERROR_LIMIT or
            maximum_angle>NORMAL_ANGLE_LIMIT or maximum_length>NORMAL_LENGTH_ERROR_LIMIT):
        raise ValueError('Attribute precision trial exceeded its error bounds')
    for before,after in zip(model['meshes'],result['meshes']):
        a = np.asarray([v['position'] for v in before['vertices']])
        b = np.asarray([v['position'] for v in after['vertices']])
        triangles = [t for mat in before['materials'] for t in mat['triangles']]
        if not triangles:continue
        t = np.asarray(triangles)
        old = np.cross(a[t[:,1]]-a[t[:,0]],a[t[:,2]]-a[t[:,0]])
        new = np.cross(b[t[:,1]]-b[t[:,0]],b[t[:,2]]-b[t[:,0]])
        # Original degenerates remain reportable; never introduce a collapse or
        # flip in a previously nonzero face to make a size target.
        valid = np.linalg.norm(old,axis=1)>0
        if np.any(np.sum(old[valid]*new[valid],axis=1)<=0):
            raise ValueError('Attribute precision introduced a collapsed or flipped face')
    report = dict(status='bounded_experiment_pending_native_pose_and_visual_validation',
                  position_divisions=divisions,position_step=step,
                  maximum_position_error_height=maximum_position,
                  maximum_uv_error=maximum_uv,maximum_normal_angle_degrees=maximum_angle,
                  maximum_normal_length_error=maximum_length,
                  changed_vertex_records=changed,held_ocular_vertex_records=held,
                  triangle_count_unchanged=True,vertex_count_unchanged=True,
                  weights_and_bone_palettes_unchanged=True,textures_unchanged=True,
                  limits=dict(position_error_height=POSITION_ERROR_LIMIT,
                              uv_error=UV_ERROR_LIMIT,normal_angle_degrees=NORMAL_ANGLE_LIMIT,
                              normal_length_error=NORMAL_LENGTH_ERROR_LIMIT))
    result['attribute_precision_report'] = report
    return result,report


def validate_native_precision(before, after, held_positions):
    """Verify decoded native records and replay identical analytical poses."""
    from model_qa.geometry import geometry,posed,AXES
    from model_qa.pipeline import POSES
    from model_qa.ocular import probes,skin
    for key in ('bone_raw','texture_raw','model_name_raw'):
        if before[key]!=after[key]:raise ValueError('Precision trial changed '+key)
    if len(before['meshes'])!=len(after['meshes']):
        raise ValueError('Precision trial changed mesh count')
    for a,b in zip(before['meshes'],after['meshes']):
        for key in ('bone_palette','stride','base_flag','rigid','opaque'):
            if a[key]!=b[key]:raise ValueError('Precision trial changed '+key)
        if len(a['vertices'])!=len(b['vertices']) or len(a['materials'])!=len(b['materials']):
            raise ValueError('Precision trial changed record counts')
        for av,bv in zip(a['vertices'],b['vertices']):
            if av['weights']!=bv['weights'] or av['color']!=bv['color']:
                raise ValueError('Precision trial changed weights or vertex colors')
            if tuple(av['position']) in held_positions and av!=bv:
                raise ValueError('Precision trial changed an ocular record')
        for am,bm in zip(a['materials'],b['materials']):
            # Layout, primitive order, all rendering bytes and all pointers are
            # unchanged: this experiment only edits float vertex attributes.
            if am['raw']!=bm['raw'] or am['strips']!=bm['strips'] or am['strip_headers']!=bm['strip_headers']:
                raise ValueError('Precision trial changed material/draw records')
    a,b = geometry(before),geometry(after)
    if not np.array_equal(a.faces,b.faces) or not np.array_equal(a.weights,b.weights):
        raise ValueError('Precision trial changed topology or dense weights')
    height = a.height
    selected = np.array([tuple(p) in held_positions for p in a.vertices@AXES])
    def compare(pa,pb):
        error = np.linalg.norm(pb.vertices-pa.vertices,axis=1)
        maximum = float(error.max()/height)
        ocular = float(error[selected].max()/height) if selected.any() else 0.
        if not np.isfinite(pb.vertices).all() or maximum>POSITION_ERROR_LIMIT*1.05 or ocular>1e-7:
            raise ValueError('Precision trial exceeded its pose error bounds')
        return dict(maximum_position_error_height=maximum,maximum_ocular_error_height=ocular,
                    finite_positions=True)
    rows={'rest':compare(a,b)}
    for name,controls in POSES.items():rows[name]=compare(posed(a,controls),posed(b,controls))
    eyes={}
    for name,probe in probes().items():
        pa,_=skin(a,probe);pb,_=skin(b,probe);eyes[name]=compare(pa,pb)
    return dict(status='pass',ordered_topology_exact=True,dense_weights_exact=True,
                opaque_rendering_and_draw_records_exact=True,
                held_ocular_vertex_records=int(selected.sum()),poses=rows,ocular_probes=eyes,
                limitation='Analytical poses on the selected PSP rig; PPSSPP gameplay validation remains required.')
