"""Simplify raw source meshes or transferred PSP-weight regions (Blender 4.3)."""
import copy
import json
import math
from pathlib import Path
import sys

import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_mesh import DETAIL_TEXTURES, RATIOS, make_regions, smooth_normals
from vertex_identity import annotate, point_key, position_key, validate_locked


def reduce(source, ratio, detail_profile=False, regional=False, preserved_regions=(), retention_reserve=None, export_face_floor=False, source_normals=False):
    if not 0 < ratio <= 1:
        raise ValueError('Reduction ratio must be between zero and one')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if regional:
        source = annotate(copy.deepcopy(source))
    owners = {}
    for entry in source['meshes']:
        for v in entry['vertices']:
            owners.setdefault(tuple(v['position']), set()).add((entry['index'],tuple(v.get('skin_id',[entry['index']]))))
    protected = {p for p, meshes in owners.items() if len(meshes) > 1}
    detail_textures = DETAIL_TEXTURES if detail_profile else set()
    if detail_profile:
        for entry in source['meshes']:
            for material in entry['materials']:
                if source['textures'][material['texture_id']].lower() in detail_textures:
                    protected.update(tuple(entry['vertices'][i]['position'])
                                     for tri in material['triangles'] for i in tri)
    result = copy.deepcopy(source)
    expected_source_points={(tuple(v['skin_id']),position_key(v)) for m in source['meshes'] for v in m['vertices']
                            if regional and v.get('skin_locked')}
    stats = []
    for entry in result['meshes']:
        if entry.get('region') in preserved_regions:
            count = sum(len(m['triangles']) for m in entry['materials'])
            stats.append({'mesh': entry['index'], 'region': entry['region'],
                          'input_triangles': count, 'output_triangles': count,
                          'requested_ratio': 1., 'target_ratio': 1., 'actual_ratio': 1.,
                          'protected_seam_positions': len({tuple(v['position']) for v in entry['vertices']} & protected),
                          'geometry_preserved_without_modifier': True})
            continue
        original_vertices = entry['vertices']
        # Keep bone-incompatible points and disconnected source domains separate.
        # Compatible corner UVs/colors remain independent Blender loop attributes.
        remap, points, source_indices, provenance = {}, [], [], []
        for v in original_vertices:
            key = point_key(v, entry['bone_palette'], entry['index']) if regional else tuple(v['position'])
            if 'normal_seam'in v:key=(key,v['normal_seam'])
            if key not in remap:
                remap[key] = len(points)
                points.append(tuple(v['position']))
                provenance.append(copy.deepcopy(v))
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
        if regional:
            identity = mesh.attributes.new(name='source_skin_id',type='INT',domain='POINT')
            for i in range(len(points)):identity.data[i].value=i
        obj = bpy.data.objects.new('source', mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh.uv_layers.new(name='UVMap')
        mesh.color_attributes.new(name='RGBA', type='FLOAT_COLOR', domain='CORNER')
        if source_normals:
            mesh.attributes.new(name='SourceNormal',type='FLOAT_VECTOR',domain='CORNER')
            for i,vertex in enumerate(corner_vertices):mesh.attributes['SourceNormal'].data[i].vector=vertex['normal']
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
        bone_groups = {}
        if regional:
            for bone in source['bones']:
                vg = obj.vertex_groups.new(name=bone['name'])
                bone_groups[vg.index] = bone['index']
                seen = set()
                for vi, vertex in enumerate(original_vertices):
                    point = source_indices[vi]
                    weight = vertex['weights'][bone['index']]
                    if point not in seen and weight > 0:
                        vg.add([point], weight, 'REPLACE')
                        seen.add(point)
        group = obj.vertex_groups.new(name='interior')
        strengths = {source_indices[i]: v.get('region_strength', 1.) for i, v in enumerate(original_vertices)}
        for i, p in enumerate(points):
            group.add([i], 0.0 if p in protected else strengths[i], 'REPLACE')
        modifier = obj.modifiers.new('PSP budget', 'DECIMATE')
        names = {source['textures'][m['texture_id']].lower() for m in entry['materials']}
        mesh_ratio = 0.30 if detail_profile and names <= {'bn_kao2', 'bn_atam', 'bn_dou'} and entry['index'] < 3 else ratio
        if regional:
            mesh_ratio = math.ceil(len(original_faces) * RATIOS[entry['region']]) / len(original_faces)
        modifier.ratio = mesh_ratio
        modifier.use_collapse_triangulate = True
        modifier.vertex_group = group.name
        modifier.vertex_group_factor = 1000
        if regional:
            # Collapse removes adjacent faces together; Blender can undershoot
            # the ratio by a face. Evaluate before applying and enforce the floor.
            minimum = math.ceil(len(original_faces) * RATIOS[entry['region']]) + (retention_reserve or {}).get(entry['region'],0)
            while True:
                bpy.context.view_layer.update()
                evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
                trial = evaluated.to_mesh()
                trial.calc_loop_triangles()
                count = len(trial.loop_triangles)
                if export_face_floor:
                    # Count the records the exporter will actually retain.
                    # Duplicate position/UV/color loop keys can otherwise make
                    # Blender's triangle count overstate the exported floor.
                    layer=trial.uv_layers['UVMap'];rgba=trial.color_attributes['RGBA']
                    count=sum(len({(trial.loops[li].vertex_index,
                        tuple(round(c,6)for c in layer.data[li].uv),
                        tuple(max(0,min(255,round(c*255)))for c in rgba.data[li].color))
                        for li in tri.loops})==3 for tri in trial.loop_triangles)
                evaluated.to_mesh_clear()
                if count >= minimum:
                    break
                if modifier.ratio >= 1.:
                    raise ValueError('Source region cannot meet the face-count floor')
                modifier.ratio = min(1., modifier.ratio + max(2, minimum-count) / len(original_faces))
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        mesh = obj.data
        for face in mesh.polygons:
            face.use_smooth = True
        mesh.update()
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
                if source_normals:
                    normal=tuple(mesh.attributes['SourceNormal'].data[li].vector)
                    length=sum(x*x for x in normal)**.5
                    if length<1e-8:raise ValueError('Source corner normal interpolation became degenerate')
                    normal=tuple(x/length for x in normal)
                texcoord = tuple(round(c, 6) for c in uv.data[li].uv)
                color = tuple(max(0, min(255, round(c * 255))) for c in colors.data[li].color)
                tid = entry['materials'][face.material_index]['texture_id']
                smoothing = tid + 1 if source['textures'][tid].lower() in detail_textures else 0
                key = (loop.vertex_index, texcoord, color, smoothing)
                if source_normals:key=key+(normal,)
                if key not in vertex_map:
                    vertex_map[key] = len(output)
                    weights = []
                    if regional:
                        weights = [0.] * source['bone_count']
                        for g in mesh.vertices[loop.vertex_index].groups:
                            if g.group in bone_groups:
                                weights[bone_groups[g.group]] = g.weight
                        total = sum(weights)
                        if total <= 0:
                            raise ValueError('Decimation lost PSP skin weights')
                        weights = [w/total for w in weights]
                    output.append({'position': position, 'normal': normal, 'uv': texcoord,
                                   'color': color, 'weights': weights, 'smoothing_group': smoothing,
                                   'source_vertex_index': loop.vertex_index})
                    if regional:
                        identity = mesh.attributes.get('source_skin_id')
                        if identity is None:raise ValueError('Decimation lost source skinning provenance')
                        pi=identity.data[loop.vertex_index].value
                        if pi<0 or pi>=len(provenance):raise ValueError('Invalid decimated source skinning provenance')
                        parent=provenance[pi]
                        for k in ('skin_id','skin_domain','source_records','skin_locked','skin_expected','skin_bind_position','normal_seam'):
                            if k in parent:output[-1][k]=copy.deepcopy(parent[k])
                        validate_locked(output[-1],entry['bone_palette'])
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
                    return Counter(tuple(sorted(tuple(Vector(vertices[i]['position'])) for i in tri)) for tri in faces)
                if geometry_keys(original_vertices, original_mat['triangles']) != geometry_keys(output, mat['triangles']):
                    raise ValueError('Reduction changed protected facial detail triangles')
        after = sum(len(t) for t in triangles)
        stats.append({'mesh': entry['index'], 'input_triangles': before,
                      'output_triangles': after, 'protected_seam_positions': len(required),
                      'requested_ratio': mesh_ratio})
        if regional:
            if after < math.ceil(before * RATIOS[entry['region']]):
                raise ValueError(f'{entry["region"]}: retained {after}/{before} faces, below requested minimum')
            stats[-1].update(region=entry['region'], target_ratio=RATIOS[entry['region']],
                             actual_ratio=after/before)
        bpy.data.objects.remove(obj, do_unlink=True)
    if regional:
        actual={(tuple(v['skin_id']),position_key(v)) for m in result['meshes'] for v in m['vertices']}
        if expected_source_points-actual:raise ValueError('Decimation lost a protected source skinning branch')
    result['triangle_count'] = sum(s['output_triangles'] for s in stats)
    result['vertex_count'] = sum(len(m['vertices']) for m in result['meshes'])
    result['reduction_report'] = {'method': 'Blender collapse with shared seam vertices protected',
                                'requested_ratio': ratio, 'input_triangles': source['triangle_count'],
                                'output_triangles': result['triangle_count'], 'meshes': stats}
    result['reduction_report']['protected_detail_textures'] = sorted(detail_textures)
    if regional:
        result['reduction_report'].pop('requested_ratio')
        result['reduction_report']['region_ratios'] = RATIOS
        if not source_normals:smooth_normals(result)
        result['regional'] = True
        result['reduction_report']['method'] = 'PSP bone-weight regions; weighted Blender collapse; area-weighted smooth normals'
        if source_normals:result['reduction_report']['method']='PSP bone-weight regions; weighted Blender collapse; source CORNER normals interpolated and renormalized without position-only averaging'
    return result


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    source, output, ratio = Path(args[0]), Path(args[1]), float(args[2])
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    model = json.loads(source.read_text())
    regional = '--regions' in args[3:]
    if regional:
        model = make_regions(model)
    result = reduce(model, ratio, detail_profile='--detail-profile' in args[3:], regional=regional)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, allow_nan=False)
    print('REDUCTION_COMPLETED', json.dumps(result['reduction_report']))


if __name__ == '__main__':
    main()
