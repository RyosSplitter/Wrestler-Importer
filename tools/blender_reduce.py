"""Simplify source geometry before sectioning and weight transfer (Blender 4.3)."""
import copy
import json
from pathlib import Path
import sys

import bpy


def reduce(source, ratio, detail_profile=False):
    if not 0 < ratio <= 1:
        raise ValueError('Reduction ratio must be between zero and one')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    owners = {}
    for entry in source['meshes']:
        for v in entry['vertices']:
            owners.setdefault(tuple(v['position']), set()).add(entry['index'])
    protected = {p for p, meshes in owners.items() if len(meshes) > 1}
    detail_textures = {'rvd_eye', 'bn_ha', 'bn_ha2', 'ts_naka'} if detail_profile else set()
    if detail_profile:
        for entry in source['meshes']:
            for material in entry['materials']:
                if source['textures'][material['texture_id']].lower() in detail_textures:
                    protected.update(tuple(entry['vertices'][i]['position'])
                                     for tri in material['triangles'] for i in tri)
    result = copy.deepcopy(source)
    stats = []
    for entry in result['meshes']:
        original_vertices = entry['vertices']
        # Weld geometric points while keeping the original per-corner UVs/colors.
        remap, points, source_indices = {}, [], []
        for v in original_vertices:
            key = tuple(v['position'])
            if key not in remap:
                remap[key] = len(points)
                points.append(key)
            source_indices.append(remap[key])
        original_faces, face_materials, corner_vertices = [], [], []
        for slot, mat in enumerate(entry['materials']):
            for tri in mat['triangles']:
                original_faces.append([source_indices[i] for i in tri])
                face_materials.append(slot)
                corner_vertices.extend(original_vertices[i] for i in tri)
        mesh = bpy.data.meshes.new('source')
        mesh.from_pydata(points, [], original_faces)
        mesh.update()
        obj = bpy.data.objects.new('source', mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh.uv_layers.new(name='UVMap')
        mesh.color_attributes.new(name='RGBA', type='FLOAT_COLOR', domain='CORNER')
        # Adding another corner attribute can invalidate an earlier RNA layer
        # reference. Resolve both layers only after all layers have been created.
        uv = mesh.uv_layers['UVMap']
        colors = mesh.color_attributes['RGBA']
        for i, vertex in enumerate(corner_vertices):
            uv.data[i].uv = vertex['uv']
            colors.data[i].color = [c / 255 for c in vertex['color']]
        for i, vertex in enumerate(corner_vertices):
            if any(abs(a - b) > 1e-6 for a, b in zip(uv.data[i].uv, vertex['uv'])):
                raise ValueError('Blender corner UV assignment changed before reduction')
            if any(abs(a - b / 255) > 1e-6 for a, b in zip(colors.data[i].color, vertex['color'])):
                raise ValueError('Blender corner color assignment changed before reduction')
        for slot, _ in enumerate(entry['materials']):
            mesh.materials.append(bpy.data.materials.new('material_' + str(slot)))
        for face, slot in zip(mesh.polygons, face_materials):
            face.material_index = slot
            face.use_smooth = True
        group = obj.vertex_groups.new(name='interior')
        for i, p in enumerate(points):
            group.add([i], 0.0 if p in protected else 1.0, 'REPLACE')
        modifier = obj.modifiers.new('PSP budget', 'DECIMATE')
        names = {source['textures'][m['texture_id']].lower() for m in entry['materials']}
        mesh_ratio = 0.30 if detail_profile and names <= {'bn_kao2', 'bn_atam', 'bn_dou'} and entry['index'] < 3 else ratio
        modifier.ratio = mesh_ratio
        modifier.use_collapse_triangulate = True
        modifier.vertex_group = group.name
        modifier.vertex_group_factor = 1000
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        mesh = obj.data
        mesh.calc_loop_triangles()
        actual_points = {tuple(v.co) for v in mesh.vertices}
        required = {tuple(mesh_point) for mesh_point in points if mesh_point in protected}
        # Blender stores float32 coordinates; compare in that same representation.
        from mathutils import Vector
        required = {tuple(Vector(p)) for p in required}
        missing = required - actual_points
        if missing:
            raise ValueError(f'Mesh {entry["index"]}: simplification moved/deleted {len(missing)} shared seam vertices')
        output, vertex_map = [], {}
        triangles = [[] for _ in entry['materials']]
        normals = [tuple(n.vector) for n in mesh.corner_normals]
        uv = mesh.uv_layers['UVMap']
        colors = mesh.color_attributes['RGBA']
        for face in mesh.loop_triangles:
            tri = []
            for li in face.loops:
                loop = mesh.loops[li]
                position = tuple(mesh.vertices[loop.vertex_index].co)
                normal = normals[li]
                texcoord = tuple(round(c, 6) for c in uv.data[li].uv)
                color = tuple(max(0, min(255, round(c * 255))) for c in colors.data[li].color)
                key = (loop.vertex_index, texcoord, color)
                if key not in vertex_map:
                    vertex_map[key] = len(output)
                    output.append({'position': position, 'normal': normal, 'uv': texcoord,
                                   'color': color, 'weights': [], 'source_vertex_index': loop.vertex_index})
                tri.append(vertex_map[key])
            if len(set(tri)) == 3:
                triangles[face.material_index].append(tri)
        before = sum(len(m['triangles']) for m in entry['materials'])
        entry['vertices'] = output
        for mat, tris in zip(entry['materials'], triangles):
            mat['triangles'] = tris
        for original_mat, mat in zip(source['meshes'][entry['index']]['materials'], entry['materials']):
            if source['textures'][mat['texture_id']].lower() in detail_textures:
                def geometry_keys(vertices, faces):
                    from collections import Counter
                    return Counter(tuple(sorted(tuple(vertices[i]['position']) for i in tri)) for tri in faces)
                if geometry_keys(original_vertices, original_mat['triangles']) != geometry_keys(output, mat['triangles']):
                    raise ValueError('Reduction changed protected facial detail triangles')
        after = sum(len(t) for t in triangles)
        stats.append({'mesh': entry['index'], 'input_triangles': before,
                      'output_triangles': after, 'protected_seam_positions': len(required),
                      'requested_ratio': mesh_ratio})
        bpy.data.objects.remove(obj, do_unlink=True)
    result['triangle_count'] = sum(s['output_triangles'] for s in stats)
    result['vertex_count'] = sum(len(m['vertices']) for m in result['meshes'])
    result['reduction_report'] = {'method': 'Blender collapse with shared seam vertices protected',
                                'requested_ratio': ratio, 'input_triangles': source['triangle_count'],
                                'output_triangles': result['triangle_count'], 'meshes': stats}
    result['reduction_report']['protected_detail_textures'] = sorted(detail_textures)
    return result


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    source, output, ratio = Path(args[0]), Path(args[1]), float(args[2])
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    result = reduce(json.loads(source.read_text()), ratio, detail_profile='--detail-profile' in args[3:])
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, allow_nan=False)
    print('REDUCTION_COMPLETED', json.dumps(result['reduction_report']))


if __name__ == '__main__':
    main()
