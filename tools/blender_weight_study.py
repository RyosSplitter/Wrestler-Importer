"""Blender helper: true bone-heat binding and independent LBS verification.

blender --background --python-exit-code 1 --python tools/blender_weight_study.py -- STUDY auto
blender --background --python-exit-code 1 --python tools/blender_weight_study.py -- STUDY review METHOD
"""
from pathlib import Path
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bpy
from mathutils import Matrix, Vector
import numpy as np

from tools.prepare_model import bone_matrices
from tools.weight_trial_review import METHODS, POSES, load_study, skin_matrices, deform, pose_metrics


CONVERSION = np.array([[1.,0,0,0], [0,0,1,0], [0,-1,0,0], [0,0,0,1]])


def primary_child(name):
    if name == 'root': return 'koshi'
    if name == 'koshi': return 'mune'
    if name == 'mune': return 'kubi'
    if name == 'kubi': return 'atama'
    for side in ('l_', 'r_'):
        if name.startswith(side):
            end = name[len(side):]
            nxt = {'sakotsu':'ninoude', 'ninoude':'kote', 'kote':'te',
                   'te':'yubi20', 'momo':'sune', 'sune':'ashi', 'ashi':'tsumasaki'}.get(end)
            if nxt: return side+nxt
            if end.startswith('yubi') and end[-1] in '01': return name[:-1]+str(int(end[-1])+1)
    return None


def create_rig(target, anatomical_tails=False):
    world = bone_matrices(target)
    byname = {b['name']:b['index'] for b in target['bones']}
    armature = bpy.data.armatures.new('PSP_%d_bone_review' % target['bone_count'])
    rig = bpy.data.objects.new('Target_PSP_Review_Rig', armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for bone, matrix in zip(target['bones'],world):
        b = armature.edit_bones.new(bone['name'])
        head = (CONVERSION @ matrix)[:3,3]
        tail = head+(CONVERSION[:3,:3]@matrix[:3,:3])@np.array([.15,0,0])
        if anatomical_tails:
            child = primary_child(bone['name'])
            if child in byname:
                proposed = (CONVERSION@world[byname[child]])[:3,3]
                if np.linalg.norm(proposed-head)>.02: tail=proposed
            elif bone['name']=='atama': tail=head+np.array([0,0,1.2])
        b.head = Vector(head)
        b.tail = Vector(tail)
        b.align_roll(Vector((CONVERSION[:3,:3]@matrix[:3,:3])@np.array([0,0,1])))
    for bone in target['bones']:
        if bone['parent']!=-1:
            armature.edit_bones[bone['name']].parent=armature.edit_bones[target['bones'][bone['parent']]['name']]
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.show_in_front=True
    return rig


def heat_eligible(name, fingers=True):
    if name in ('root','koshi','mune','kubi','atama'): return True
    if name.startswith(('l_','r_')):
        tail=name[2:]
        return tail in ('sakotsu','ninoude','kote','te','momo','sune','ashi','tsumasaki') or (fingers and tail.startswith('yubi'))
    return False


def automatic(root):
    source,target,aligned,positions,_,_,_=load_study(root)
    # Weld a disposable binding proxy. Final source vertex/triangle/UV buffers
    # stay unchanged; each original vertex receives its proxy vertex's weights.
    lookup={}; inverse=[]; unique=[]
    for position in positions:
        key=tuple(position)
        if key not in lookup:
            lookup[key]=len(unique);unique.append(position)
        inverse.append(lookup[key])
    inverse=np.array(inverse)
    faces=[];offset=0
    for mesh in aligned['meshes']:
        for mat in mesh['materials']:
            for triangle in mat['triangles']:
                mapped=tuple(int(inverse[offset+i]) for i in triangle)
                if len(set(mapped))==3: faces.append(mapped)
        offset+=len(mesh['vertices'])
    attempts=[]
    for fingers in (True,False):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        rig=create_rig(target,anatomical_tails=True)
        for b in rig.data.bones: b.use_deform=heat_eligible(b.name,fingers)
        mesh=bpy.data.meshes.new('Disposable_seam_welded_heat_proxy')
        mesh.from_pydata([tuple(CONVERSION[:3,:3]@p) for p in unique],[],faces)
        mesh.update()
        proxy=bpy.data.objects.new(mesh.name,mesh)
        bpy.context.collection.objects.link(proxy)
        bpy.ops.object.select_all(action='DESELECT')
        proxy.select_set(True);rig.select_set(True)
        bpy.context.view_layer.objects.active=rig
        error=None
        try: bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        except RuntimeError as exc: error=str(exc)
        index={b['name']:b['index'] for b in target['bones']}
        weights=np.zeros((len(unique),target['bone_count']))
        for vertex in mesh.vertices:
            for group in vertex.groups:
                name=proxy.vertex_groups[group.group].name
                if name in index:weights[vertex.index,index[name]]=group.weight
        sums=weights.sum(axis=1)
        attempt={'binding':'Blender 4.3.2 ARMATURE_AUTO bone heat',
                 'fingers_enabled':fingers,'deforming_bones':sum(b.use_deform for b in rig.data.bones),
                 'unweighted_proxy_vertices':int(np.count_nonzero(sums<=1e-8)),
                 'error':error}
        attempts.append(attempt)
        print('BINDING ATTEMPT',json.dumps(attempt),flush=True)
        if error or np.any(sums<=1e-8): continue
        weights/=sums[:,None]
        order=np.argsort(weights,axis=1)
        np.put_along_axis(weights,order[:,:-4],0,axis=1)
        retained=weights.sum(axis=1)
        weights/=retained[:,None]
        output=weights[inverse]
        assert output.shape==(len(positions),target['bone_count'])
        assert np.isfinite(output).all() and np.max(np.abs(output.sum(axis=1)-1))<1e-8
        np.savez_compressed(root/'automatic-weights.npz',weights=output)
        report={'method':'Blender ARMATURE_AUTO bone-heat rebinding on a disposable welded proxy',
                'attempts':attempts,'proxy_vertices':len(unique),'proxy_faces':len(faces),
                'output_vertices':len(positions),'source_geometry_modified':False,
                'max_influences':4,'max_weight_mass_pruned':float(np.max(1-retained)),
                'body_and_finger_bones_used':fingers,'facial_and_twist_helpers_not_heat_bound':True,
                'target_rig_bone_count':target['bone_count'],
                'note':'Bone segment tails inferred from target anatomy for binding only; facial/helper bones '
                       'remain in the target rig but have no automatic weight seeds. No source or PSP donor weights used.'}
        (root/'automatic-binding-report.json').write_text(json.dumps(report,indent=2)+'\n')
        bpy.ops.wm.save_as_mainfile(filepath=str(root/'automatic-binding-proxy.blend'))
        return
    (root/'automatic-binding-failure.json').write_text(json.dumps({'attempts':attempts},indent=2)+'\n')
    raise RuntimeError('Blender bone heat could not bind every proxy vertex; no replacement weights fabricated')


def audit_automatic(root):
    # The saved proxy retains Blender's full, unpruned vertex groups. Compare
    # those with the four-influence trial to isolate the effect of pruning.
    source,target,aligned,positions,originals,sw,alignment=load_study(root)
    bpy.ops.wm.open_mainfile(filepath=str(root/'automatic-binding-proxy.blend'))
    proxy=bpy.data.objects['Disposable_seam_welded_heat_proxy']
    byname={b['name']:b['index'] for b in target['bones']}
    unique_weights=np.zeros((len(proxy.data.vertices),target['bone_count']))
    for vertex in proxy.data.vertices:
        for group in vertex.groups:
            name=proxy.vertex_groups[group.group].name
            if name in byname:unique_weights[vertex.index,byname[name]]=group.weight
    unique_weights/=unique_weights.sum(axis=1)[:,None]
    lookup={};inverse=[]
    for point in positions:
        key=tuple(point)
        if key not in lookup:lookup[key]=len(lookup)
        inverse.append(lookup[key])
    weights=unique_weights[inverse]
    assert len(lookup)==len(unique_weights)
    pruned=np.load(root/'automatic-weights.npz')['weights']
    report={'purpose':'Separate raw Blender heat binding from four-influence pruning; primary trial 5 unchanged',
            'unpruned_max_active_influences':int(np.max(np.count_nonzero(weights>1e-7,axis=1))),
            'poses':{}}
    for name,pose in POSES.items():
        unpruned=deform(target,positions,weights,pose)
        after=deform(target,positions,pruned,pose)
        original=deform(source,originals,sw,pose)
        reference=alignment['scale']*original@np.array(alignment['rotation']).T+np.array(alignment['translation'])
        delta=np.linalg.norm(after-unpruned,axis=1)
        report['poses'][name]={'unpruned_metrics':pose_metrics(aligned,unpruned,positions,reference),
                               'pruning_displacement_rms':float(np.sqrt(np.mean(delta**2))),
                               'pruning_displacement_max':float(delta.max())}
    (root/'automatic-unpruned-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('UNPRUNED AUDIT',json.dumps(report),flush=True)


def build_review(root,method):
    if method==1: raise ValueError('Incomplete direct mapping is a baked diagnostic, not a valid 77-bone Blender rig')
    source,target,aligned,positions,_,_,_=load_study(root)
    folder=root/('method-%d-'%method+METHODS[method])
    weights=np.load(folder/'weights.npz')['weights']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rig=create_rig(target)
    objects=[];offset=0
    for entry in aligned['meshes']:
        count=len(entry['vertices'])
        mesh=bpy.data.meshes.new('Source_mesh_'+str(entry['index']))
        points=[tuple(CONVERSION[:3,:3]@p) for p in positions[offset:offset+count]]
        faces=[t for mat in entry['materials'] for t in mat['triangles']]
        mesh.from_pydata(points,[],faces);mesh.update()
        if len(mesh.vertices)!=count or len(mesh.polygons)!=len(faces):
            raise ValueError('Blender changed source geometry counts during review import')
        for p in mesh.polygons:p.use_smooth=True
        uv=mesh.uv_layers.new(name='Original_source_UV')
        for polygon in mesh.polygons:
            for loop in polygon.loop_indices:
                uv.data[loop].uv=entry['vertices'][mesh.loops[loop].vertex_index]['uv']
        obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
        for b in target['bones']:
            values=weights[offset:offset+count,b['index']]
            indices=np.flatnonzero(values>0)
            if len(indices):
                group=obj.vertex_groups.new(name=b['name'])
                for i in indices:group.add([int(i)],float(values[i]),'REPLACE')
        modifier=obj.modifiers.new('Target_PSP_weights','ARMATURE');modifier.object=rig
        obj.parent=rig;objects.append(obj)
        face_offset=0
        for mat_entry in entry['materials']:
            texture=aligned['textures'][mat_entry['texture_id']]
            material=bpy.data.materials.get(texture)
            if material is None:
                material=bpy.data.materials.new(texture);material.use_nodes=True
                image=material.node_tree.nodes.new('ShaderNodeTexImage')
                image.image=bpy.data.images.load(str(folder/(texture+'.png')),check_existing=True)
                material.node_tree.links.new(image.outputs['Color'],material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
                material.node_tree.nodes.active=image
            mesh.materials.append(material)
            for polygon in mesh.polygons[face_offset:face_offset+len(mat_entry['triangles'])]:polygon.material_index=len(mesh.materials)-1
            face_offset+=len(mat_entry['triangles'])
        offset+=count
    if sum(len(o.data.vertices) for o in objects)!=aligned['vertex_count'] or sum(len(o.data.polygons) for o in objects)!=aligned['triangle_count']:
        raise ValueError('Review geometry totals do not match the original source')
    rest={b.name:np.array(b.matrix_local) for b in rig.data.bones}
    validation={}
    scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=61
    frames={'rest':1,'elbow-flex':21,'arms-up':41,'knees-bent':61}
    for name,pose in POSES.items():
        scene.frame_set(frames[name])
        motion=skin_matrices(target,pose)
        desired={b['name']:CONVERSION@motion[b['index']]@np.linalg.inv(CONVERSION)@rest[b['name']] for b in target['bones']}
        for b in target['bones']:
            bone=rig.pose.bones[b['name']]
            if b['parent']==-1:
                basis=np.linalg.inv(rest[b['name']])@desired[b['name']]
            else:
                parent=target['bones'][b['parent']]['name']
                local=np.linalg.inv(rest[parent])@rest[b['name']]
                basis=np.linalg.inv(local)@np.linalg.inv(desired[parent])@desired[b['name']]
            bone.matrix_basis=Matrix(basis.tolist())
            bone.rotation_mode='QUATERNION'
            bone.keyframe_insert('location');bone.keyframe_insert('rotation_quaternion');bone.keyframe_insert('scale')
        bpy.context.view_layer.update()
        graph=bpy.context.evaluated_depsgraph_get()
        actual=[]
        for obj in objects:
            evaluated=obj.evaluated_get(graph)
            actual.extend(tuple(evaluated.matrix_world@v.co) for v in evaluated.data.vertices)
        actual=np.array(actual)
        expected=np.load(folder/(name+'-positions.npy'))@CONVERSION[:3,:3].T
        error=float(np.max(np.linalg.norm(actual-expected,axis=1)))
        if error>2e-5:raise ValueError('Blender/LBS pose mismatch '+name+': '+str(error))
        validation[name]={'max_position_difference_from_blender':error,'vertices_checked':len(actual)}
    for image in bpy.data.images:
        if image.source=='FILE':image.pack()
    scene.frame_set(21)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/'weighted-review.blend'))
    (folder/'blender-validation.json').write_text(json.dumps({'poses':validation,'target_bones':len(rig.data.bones),
        'source_geometry_count_preserved':True,'rig_is_review_only_not_a_psp_skeleton_export':True},indent=2)+'\n')
    print('INDEPENDENT BLENDER CHECK',json.dumps(validation),flush=True)


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    study=Path(args[0]).resolve()
    if args[1]=='auto':automatic(study)
    elif args[1]=='review':build_review(study,int(args[2]))
    elif args[1]=='audit-auto':audit_automatic(study)
    else:raise ValueError('Expected auto or review')
