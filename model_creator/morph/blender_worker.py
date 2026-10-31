"""Headless Blender shape keys with stable native-record vertex IDs."""
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

# Script is bundled as data for Blender's Python, separate from frozen imports.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from model_creator.morph.deform import CONTROLS,ENGINE,evaluate,positions


def run(input_path,output_path):
    data=Path(input_path).read_bytes();job=json.loads(data)
    p=np.asarray(job['positions'],dtype=float);faces=job['faces']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh=bpy.data.meshes.new('Native morph records');mesh.from_pydata(p.tolist(),[],faces);mesh.update()
    ids=mesh.attributes.new(name='native_record_id',type='INT',domain='POINT')
    for i in range(len(p)):ids.data[i].value=i
    obj=bpy.data.objects.new('Morph Studio',mesh);bpy.context.collection.objects.link(obj)
    obj.shape_key_add(name='Basis')
    for control in CONTROLS:
        key=obj.shape_key_add(name=control);key.slider_min=-1;key.slider_max=1
        target=positions(p,job['anchors'],job['height'],{control:1})
        for i,point in enumerate(target):key.data[i].co=point
        key.value=job['parameters'][control]
    bpy.context.view_layer.update()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());result=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=bpy.context.evaluated_depsgraph_get())
    try:
        if len(result.vertices)!=len(p) or [list(poly.vertices) for poly in result.polygons]!=faces:
            raise ValueError('Blender changed morph topology')
        if [v.value for v in result.attributes['native_record_id'].data]!=list(range(len(p))):raise ValueError('Blender changed native record identity')
        output=np.array([v.co[:] for v in result.vertices]);expected,normals=evaluate(p,job['normals'],job['anchors'],job['height'],job['parameters'])
        error=float(np.linalg.norm(output-expected,axis=1).max())
        if error>job['height']*2e-6:raise ValueError('Blender/preview morph disagreement')
        Path(output_path).write_text(json.dumps(dict(engine=ENGINE,input_sha256=hashlib.sha256(data).hexdigest(),
            positions=output.tolist(),normals=normals.tolist(),preview_error=error,
            shape_keys=len(CONTROLS),vertex_ids_exact=True,faces_exact=True),allow_nan=False),encoding='utf-8')
    finally:evaluated.to_mesh_clear()


if __name__=='__main__':run(*sys.argv[sys.argv.index('--')+1:])
