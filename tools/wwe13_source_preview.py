"""Provisional diffuse-only source preview, not a PSP conversion/game renderer.

Uses the inspected sample's main + hair + eye shells and color atlas. Shader
binding, winding, cutouts, facial controllers and source vertex tint are not
reproduced. No PAC/YOBJ is changed; OBJ is static and has no skinning.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from desktop.preview import render
from tools.wwe13_inspect import read_jboy


def preview(bundle, output, resolution=640):
    output.mkdir(parents=True, exist_ok=False)
    meshes = []
    for section in (0, 10000, 20002):
        model = read_jboy((bundle / f'section_{section:05d}.bin').read_bytes())
        for mesh in model['meshes']:
            mesh['index'] = len(meshes)
            for mat in mesh['materials']:
                mat['texture_id'] = 0  # Explicit provisional color-only override.
            meshes.append(mesh)
    atlas = Image.open(bundle / 'section_00012-texture-00.png').convert('RGBA')
    atlas.save(output / 'color.png')
    colors = np.array(atlas)
    indices = np.arange(atlas.width * atlas.height).reshape(atlas.height, atlas.width)
    decoded = (indices, colors.reshape((-1, 4)))
    merged = dict(meshes=meshes, texture_names=['color'])
    for view in ('front', 'back', 'left', 'right', 'front-left'):
        im = render(merged, {'color': b''}, view, resolution, gim_reader=lambda raw: decoded)
        draw = ImageDraw.Draw(im)
        draw.rectangle((0, 0, resolution, 34), fill=(72, 72, 72))
        draw.text((14, 14), 'WWE 13 SOURCE RESEARCH | ' + view.upper(), fill='white')
        draw.rectangle((0, resolution - 34, resolution, resolution), fill=(72, 72, 72))
        draw.text((14, resolution - 25), 'Provisional diffuse-only CPU preview | NOT a PSP conversion', fill='white')
        im.save(output / (view + '.png'))
    # Rotate by pi around X for viewing, preserving scale/proportions.
    with (output / 'source.obj').open('x') as obj:
        obj.write('# Provisional source geometry. No skeleton. Proper rotation (x,-y,-z).\nmtllib source.mtl\n')
        base = 1
        for mesh in meshes:
            obj.write(f"o source_mesh_{mesh['index']:02d}\nusemtl diffuse_only\n")
            for v in mesh['vertices']:
                x, y, z = v['position']; obj.write(f'v {x} {-y} {-z}\n')
            for v in mesh['vertices']:
                u, vcoord = v['uv']; obj.write(f'vt {u} {1-vcoord}\n')
            for v in mesh['vertices']:
                x, y, z = v['normal']; obj.write(f'vn {x} {-y} {-z}\n')
            for mat in mesh['materials']:
                for face in mat['triangles']:
                    obj.write('f ' + ' '.join(f'{base+i}/{base+i}/{base+i}' for i in face) + '\n')
            base += len(mesh['vertices'])
    (output / 'source.mtl').write_text('newmtl diffuse_only\nKd 1 1 1\nmap_Kd color.png\n')
    (output / 'preview-notes.json').write_text(json.dumps(dict(
        source_sections=[0, 10000, 20002], source_coordinates_preserved_except_proper_view_rotation=True,
        projection='Orthographic CPU; two-sided preview; unverified source strip winding',
        material_policy='All shells assigned section 12 color DDS; not native shader binding',
        unsupported=['source shader lighting', 'normal maps', 'hair anisotropy/cutout policy',
                     'eye reflections', 'vertex tint', 'facial/cloth/hair animation'],
        psp_conversion=False), indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    preview(a.bundle, a.output)
