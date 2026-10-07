"""Run with Blender to build a review rig and check deformation of prepared JSON.

blender --background --python-exit-code 1 --python tools/blender_validate.py -- INPUT.json OUTPUT_DIRECTORY
The rig is for review, not a PSP skeleton exporter. It preserves the imported
hierarchy, using a constant coordinate/bone-axis change for Blender display.
"""
import colorsys
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Euler, Matrix, Vector


def world_matrices(bones):
    cache = {}
    def get(index):
        if index not in cache:
            bone = bones[index]
            matrix = Euler(bone['rotation'], 'XYZ').to_matrix().to_4x4()
            matrix.translation = Vector(bone['local_position'])
            cache[index] = matrix if bone['parent'] == -1 else get(bone['parent']) @ matrix
        return cache[index]
    return [get(i) for i in range(len(bones))]


def build(model, textures=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    conversion = Matrix.Rotation(-math.pi / 2, 4, 'X')
    world = world_matrices(model['bones'])
    armature = bpy.data.armatures.new('PSP_Review_Armature')
    rig = bpy.data.objects.new('Armature', armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for bone, matrix in zip(model['bones'], world):
        edit = armature.edit_bones.new(bone['name'])
        edit.head = conversion @ matrix.translation
        direction = (conversion.to_3x3() @ matrix.to_3x3()) @ Vector((0.15, 0, 0))
        edit.tail = edit.head + direction
        edit.align_roll((conversion.to_3x3() @ matrix.to_3x3()) @ Vector((0, 0, 1)))
    for bone in model['bones']:
        if bone['parent'] != -1:
            armature.edit_bones[bone['name']].parent = armature.edit_bones[model['bones'][bone['parent']]['name']]
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.show_in_front = True
    objects = []
    for entry in model['meshes']:
        name = f"part_{entry['target_part']:02d}_chunk_{entry['part_chunk']:02d}"
        mesh = bpy.data.meshes.new(name)
        positions = [tuple(conversion @ Vector(v['position'])) for v in entry['vertices']]
        faces = [t for material in entry['materials'] for t in material['triangles']]
        mesh.from_pydata(positions, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        uv = mesh.uv_layers.new(name='UVMap')
        for polygon in mesh.polygons:
            for li in polygon.loop_indices:
                uv.data[li].uv = entry['vertices'][mesh.loops[li].vertex_index]['uv']
        for slot, index in enumerate(entry['bone_palette']):
            if not 0 <= index < model['bone_count']:
                raise ValueError('Outside target bone table')
            group = obj.vertex_groups.new(name=model['bones'][index]['name'])
            for vi, vertex in enumerate(entry['vertices']):
                if vertex['weights'][slot] > 0:
                    group.add([vi], vertex['weights'][slot], 'REPLACE')
        modifier = obj.modifiers.new(name='PSP weights review', type='ARMATURE')
        modifier.object = rig
        obj.parent = rig
        rgb = colorsys.hsv_to_rgb((entry['target_part'] * 0.61803398875) % 1, 0.35, 0.75)
        if textures:
            offset = 0
            for slot, source_material in enumerate(entry['materials']):
                tid = source_material['texture_id']
                material_name = f'source_texture_{tid:02d}'
                material = bpy.data.materials.get(material_name)
                if material is None:
                    material = bpy.data.materials.new(material_name)
                    material.use_nodes = True
                    image = material.node_tree.nodes.new('ShaderNodeTexImage')
                    image.image = bpy.data.images.load(str(textures / f'texture_{tid:02d}.png'), check_existing=True)
                    material.node_tree.links.new(image.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
                    material.node_tree.nodes.active = image
                mesh.materials.append(material)
                for polygon in mesh.polygons[offset:offset + len(source_material['triangles'])]:
                    polygon.material_index = slot
                offset += len(source_material['triangles'])
        else:
            material = bpy.data.materials.new(name + '_section_color')
            material.diffuse_color = (*rgb, 1)
            mesh.materials.append(material)
        objects.append(obj)
    return rig, objects


def evaluated_positions(objects):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    return [[tuple(obj.matrix_world @ v.co) for v in obj.evaluated_get(graph).data.vertices] for obj in objects]


def check(model, objects, positions, rest):
    maximum_seam = 0
    seams = {}
    stretch = []
    edge_details = []
    moved = 0
    for entry, obj, actual, original in zip(model['meshes'], objects, positions, rest):
        if len(actual) != len(entry['vertices']):
            raise ValueError('Vertex count changed during deformation')
        for vertex, point, baseline in zip(entry['vertices'], actual, original):
            if not all(math.isfinite(x) for x in point):
                raise ValueError('Non-finite pose coordinate')
            moved += (Vector(point) - Vector(baseline)).length > 1e-4
            key = tuple(vertex['position'])
            if key in seams:
                maximum_seam = max(maximum_seam, (Vector(point) - Vector(seams[key])).length)
            else:
                seams[key] = point
        for edge in obj.data.edges:
            a, b = edge.vertices
            length = (Vector(original[a]) - Vector(original[b])).length
            if length > 1e-5:
                posed = (Vector(actual[a]) - Vector(actual[b])).length
                ratio = posed / length
                stretch.append(ratio)
                edge_details.append({'mesh': obj.name, 'vertices': [int(a), int(b)],
                                     'rest_length': length, 'posed_length': posed, 'ratio': ratio})
    if maximum_seam > 1e-4:
        raise ValueError(f'Seams separated by {maximum_seam}')
    stretch.sort()
    return {'moved_vertices': moved, 'max_duplicate_position_separation': maximum_seam,
            'edge_length_ratio_p95': stretch[int((len(stretch) - 1) * 0.95)],
            'edge_length_ratio_max': max(stretch),
            'largest_edge_changes': sorted(edge_details, key=lambda e: -e['ratio'])[:8],
            'note': 'Finite coordinates and seam continuity are structural checks, not animation quality approval'}


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    input_file, output = Path(args[0]).resolve(), Path(args[1]).resolve()
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    model = json.loads(input_file.read_text())
    output.mkdir(parents=True)
    textures = Path(args[2]).resolve() if len(args) > 2 else None
    rig, objects = build(model, textures)
    counts = {'meshes': len(objects), 'vertices': sum(len(o.data.vertices) for o in objects),
              'triangles': sum(len(o.data.polygons) for o in objects), 'bones': len(rig.data.bones)}
    assert counts == {'meshes': model['mesh_count'], 'vertices': model['vertex_count'],
                      'triangles': model['triangle_count'], 'bones': model['bone_count']}
    rest = evaluated_positions(objects)
    # Camera and colored sections assist review; no game texture is implied.
    bpy.ops.object.camera_add(location=(0, -42, 0))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 24
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'TEXTURE' if textures else 'MATERIAL'
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.render.resolution_x = scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    if textures:
        for image in bpy.data.images:
            if image.source == 'FILE':
                image.pack()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'hctp-psp-review.blend'))
    poses = {'t-pose': {},
             'arms-raised': {'l_ninoude': (0, 0, -0.9), 'r_ninoude': (0, 0, 0.9)},
             'elbows-knees-bent': {'l_kote': (0, 0, 1.2), 'r_kote': (0, 0, -1.2),
                                   'l_sune': (1.0, 0, 0), 'r_sune': (1.0, 0, 0)}}
    outcomes = {}
    for name, rotations in poses.items():
        for bone in rig.pose.bones:
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = rotations.get(bone.name, (0, 0, 0))
        positions = evaluated_positions(objects)
        outcomes[name] = check(model, objects, positions, rest)
        if rotations and outcomes[name]['moved_vertices'] == 0:
            raise ValueError('Test pose did not deform the model')
        scene.render.filepath = str(output / (name + '.png'))
        bpy.ops.render.render(write_still=True)
    report = {'counts': counts, 'poses': outcomes,
              'limitations': ['Review rig uses Blender bone axes; native PSP skeleton is retained in prepared.json',
                              'These pose checks do not exercise the PSP animation engine']}
    (output / 'deformation-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('DEFORMATION_CHECK_COMPLETED', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
