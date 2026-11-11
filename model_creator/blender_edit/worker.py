"""Blender-only worker: explicit scene contract; no embedded scripts required."""
import hashlib
import json
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector

C=Matrix(((1,0,0),(0,0,1),(0,-1,0)))

def material_signature(mat):
    def value(v):
        if isinstance(v,(str,bool,int,float)):return v
        try:return list(v)
        except TypeError:return None
    tree=mat.node_tree
    result=dict(nodes=sorted((n.name,n.bl_idname,getattr(getattr(n,'image',None),'name',None),
        [(socket.name,value(socket.default_value))for socket in n.inputs if hasattr(socket,'default_value')],
        [(k,getattr(n,k))for k in ('extension','interpolation','projection')if hasattr(n,k)])for n in tree.nodes),
        links=sorted((l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name)for l in tree.links))
    return json.loads(json.dumps(result))

def create(job,folder):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    images=[];materials=[]
    for i,t in enumerate(job['textures']):
        image=bpy.data.images.load(str(folder/t['file']),check_existing=False);image.name=f'PSP Image {i:03d}';image.pack();images.append(image)
        mat=bpy.data.materials.new(f'PSP Material {i:03d}');mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear()
        tex=nodes.new('ShaderNodeTexImage');tex.name='Texture';tex.image=image
        shader=nodes.new('ShaderNodeBsdfPrincipled');shader.name='Shader';shader.inputs['Roughness'].default_value=.7
        output=nodes.new('ShaderNodeOutputMaterial');output.name='Output';links=mat.node_tree.links
        links.new(tex.outputs['Color'],shader.inputs['Base Color']);links.new(tex.outputs['Alpha'],shader.inputs['Alpha']);links.new(shader.outputs['BSDF'],output.inputs['Surface']);materials.append(mat)
    arm=bpy.data.armatures.new('PSP Rig');rig=bpy.data.objects.new('PSP Rig',arm);bpy.context.collection.objects.link(rig);rig.show_in_front=True
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for b in job['bones']:
        bone=arm.edit_bones.new(b['name']);bone.head=C@Vector(b['position']);bone.tail=bone.head+Vector((0,0,job['height']*.025))
    for b in job['bones']:
        if b['parent']>=0:arm.edit_bones[b['name']].parent=arm.edit_bones[job['bones'][b['parent']]['name']]
    bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)
    for i,row in enumerate(job['meshes']):
        mesh=bpy.data.meshes.new(f'PSP Mesh {i:03d}');mesh.from_pydata([C@Vector(v['position']) for v in row['vertices']],[],row['faces']);mesh.update()
        obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
        obj['psp_mesh_id']=i;obj.lock_location=(True,)*3;obj.lock_rotation=(True,)*3;obj.lock_scale=(True,)*3
        ids=mesh.attributes.new('psp_record_id','INT','POINT')
        for n,v in enumerate(ids.data):v.value=n
        for mat in materials:mesh.materials.append(mat)
        uv=mesh.uv_layers.new(name='PSP UV')
        for poly,tid in zip(mesh.polygons,row['texture_ids']):
            poly.material_index=tid;poly.use_smooth=True
            for li in poly.loop_indices:
                u,v=row['vertices'][mesh.loops[li].vertex_index]['uv'];uv.data[li].uv=(u,1-v)
        mesh.normals_split_custom_set_from_vertices([C@Vector(v['normal']) for v in row['vertices']])
        for b in job['bones']:obj.vertex_groups.new(name=b['name'])
        for vi,v in enumerate(row['vertices']):
            for bone,weight in zip(row['palette'],v['weights']):
                if weight:obj.vertex_groups[bone].add([vi],weight,'REPLACE')
        mod=obj.modifiers.new('PSP skinning','ARMATURE');mod.object=rig
    bpy.context.scene['psp_baseline_sha256']=job['baseline_sha256']
    for obj in bpy.data.objects:
        if obj.type=='MESH':obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.shading.type='MATERIAL';area.spaces.active.region_3d.view_distance=job['height']*1.5
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/'model.blend'))
    return dict(bones=[dict(name=b.name,parent=b.parent.name if b.parent else None,matrix=[list(r) for r in b.matrix_local]) for b in arm.bones],materials=[material_signature(m) for m in materials])

def close_matrix(a,b):return all(abs(x-y)<1e-5 for ra,rb in zip(a,b) for x,y in zip(ra,rb))

def extract(job,contract,blend,folder):
    bpy.ops.wm.open_mainfile(filepath=str(blend),load_ui=False,use_scripts=False)
    if bpy.context.scene.get('psp_baseline_sha256')!=job['baseline_sha256']:raise ValueError('Blender file belongs to a different model')
    rig=bpy.data.objects.get('PSP Rig')
    if rig is None or rig.type!='ARMATURE' or not close_matrix(rig.matrix_world,Matrix.Identity(4)):raise ValueError('PSP rig object changed')
    if len(rig.data.bones)!=len(contract['bones']):raise ValueError('Bone count changed')
    for expected,bone in zip(contract['bones'],rig.data.bones):
        if bone.name!=expected['name'] or (bone.parent.name if bone.parent else None)!=expected['parent'] or not close_matrix(bone.matrix_local,expected['matrix']):raise ValueError('Bone names, hierarchy or rest transforms changed')
        if not close_matrix(rig.pose.bones[bone.name].matrix_basis,Matrix.Identity(4)):raise ValueError('Return the rig to its rest pose before importing')
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if len(objects)!=len(job['meshes']):raise ValueError('Mesh objects were added or removed')
    results=[]
    for index,row in enumerate(job['meshes']):
        obj=bpy.data.objects.get(f'PSP Mesh {index:03d}')
        if obj not in objects or obj.get('psp_mesh_id')!=index:raise ValueError('Mesh identity changed')
        if not close_matrix(obj.matrix_world,Matrix.Identity(4)):raise ValueError('Apply object transforms before importing; use Edit Mode for proportions')
        mesh=obj.data
        if mesh.shape_keys is not None:raise ValueError('Apply shape keys to the mesh before importing')
        if len(obj.modifiers)!=1 or obj.modifiers[0].type!='ARMATURE' or obj.modifiers[0].object!=rig:raise ValueError('Only the original armature modifier is supported')
        ids=mesh.attributes.get('psp_record_id')
        if len(mesh.vertices)!=len(row['vertices']) or ids is None or ids.domain!='POINT' or [a.value for a in ids.data]!=list(range(len(row['vertices']))):raise ValueError('Vertex count/order or native record IDs changed; topology edits are unsupported')
        if [list(p.vertices) for p in mesh.polygons]!=row['faces']:raise ValueError('Faces or topology changed')
        if [p.material_index for p in mesh.polygons]!=row['texture_ids']:raise ValueError('Material assignments changed')
        if len(mesh.materials)!=len(job['textures']):raise ValueError('Material slots changed')
        if any(slot.link!='DATA' or slot.material!=mesh.materials[i]for i,slot in enumerate(obj.material_slots)):raise ValueError('Object material overrides changed')
        for i,mat in enumerate(mesh.materials):
            if mat is None or material_signature(mat)!=contract['materials'][i]:raise ValueError('Texture bindings or material shader graph changed')
        if [g.name for g in obj.vertex_groups]!=[b['name'] for b in job['bones']]:raise ValueError('Skinning groups changed')
        if len(mesh.uv_layers)!=1 or mesh.uv_layers[0].name!='PSP UV':raise ValueError('Keep the original PSP UV layer')
        uv=[None]*len(mesh.vertices)
        for loop,tex in zip(mesh.loops,mesh.uv_layers[0].data):
            value=(float(tex.uv.x),1-float(tex.uv.y));vi=loop.vertex_index
            if uv[vi] is not None and max(abs(a-b) for a,b in zip(uv[vi],value))>1e-6:raise ValueError('A UV edit split one native vertex; keep its UV corners together')
            uv[vi]=value
        points=[];normals=[];uvs=[]
        changed=any((C.transposed()@v.co-Vector(old['position'])).length>1e-7 for v,old in zip(mesh.vertices,row['vertices']))
        # Rotate the original normal field with the local surface change.
        # Recomputing each native draw separately would create shading seams at
        # palette boundaries and alter even a uniform scale's appearance.
        old_area=[Vector((0,0,0))for _ in mesh.vertices];new_area=[Vector((0,0,0))for _ in mesh.vertices]
        if changed:
            original=[C@Vector(v['position'])for v in row['vertices']]
            for a,b,c in row['faces']:
                old_cross=(original[b]-original[a]).cross(original[c]-original[a])
                new_cross=(mesh.vertices[b].co-mesh.vertices[a].co).cross(mesh.vertices[c].co-mesh.vertices[a].co)
                for vi in (a,b,c):old_area[vi]+=old_cross;new_area[vi]+=new_cross
        for vi,(v,old) in enumerate(zip(mesh.vertices,row['vertices'])):
            weights={g.group:g.weight for g in v.groups if g.weight>1e-8};wanted={b:a for b,a in zip(row['palette'],old['weights']) if a>1e-8}
            if weights.keys()!=wanted.keys() or any(abs(weights[b]-wanted[b])>2e-6 for b in wanted):raise ValueError('Skin weights changed')
            normal=C@Vector(old['normal'])
            if changed and min(old_area[vi].length,new_area[vi].length)>1e-10:normal=old_area[vi].rotation_difference(new_area[vi])@normal
            points.append(list(C.transposed()@v.co));normals.append(list(C.transposed()@normal) if changed else old['normal']);uvs.append(uv[vi] if uv[vi] is not None else old['uv'])
        results.append(dict(positions=points,normals=normals,uv=uvs))
    textures=[]
    for i,t in enumerate(job['textures']):
        image=bpy.data.images.get(f'PSP Image {i:03d}')
        if image is None or list(image.size)!=t['size']:raise ValueError('Texture image was removed or resized')
        image.filepath_raw=str(folder/f'texture_{i:03d}.png');image.file_format='PNG';image.save();textures.append(image.filepath_raw)
    return dict(meshes=results,textures=textures,baseline_sha256=job['baseline_sha256'])

def main():
    mode,job_path,output,*extra=sys.argv[sys.argv.index('--')+1:];job=json.loads(Path(job_path).read_text());folder=Path(output).parent
    result=create(job,folder) if mode=='create' else extract(job,json.loads(Path(extra[0]).read_text()),Path(extra[1]),folder)
    Path(output).write_text(json.dumps(result,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main()
