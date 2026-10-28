"""Painted wrist/knee borders between faces using a single material."""
import copy
import unittest

import numpy as np

from desktop.texture_edges import clothing_edges


def model():
    bones=[dict(index=0,name='koshi',parent=-1),dict(index=1,name='l_sakotsu',parent=0)]
    meshes=[]
    for i in range(2):
        low,high=(-1.,0.) if i==0 else (0.,1.)
        u0,u1=(0.,.4) if i==0 else (.6,.99)
        ps=[[low,0,0],[high,0,0],[high,1,0],[low,1,0]]
        uvs=[[u0,0],[u1,0],[u1,.99],[u0,.99]]
        meshes.append(dict(index=i,bone_palette=[1],
            vertices=[dict(position=p,uv=uv,weights=[1.]) for p,uv in zip(ps,uvs)],
            materials=[dict(texture_id=0,triangles=[[0,1,2],[0,2,3]])]))
    return dict(bones=bones,textures=['map'],meshes=meshes)


def image():
    im=np.full((32,32,4),255,np.uint8)
    im[:,:,:3]=[180,130,110]
    im[:,:16,:3]=[10,10,10]
    return im


class PaintedEdgeTests(unittest.TestCase):
    def test_adjacent_dark_and_skin_faces_are_preserved_without_material_split(self):
        r=clothing_edges(model(),{'map':image()})
        self.assertEqual(r['faces'],[[0,0,0,0],[1,0,0,1]])
        self.assertEqual(r['contrasting_edges'],1)
        self.assertEqual(r['per_texture'],{'map':2})

    def test_smooth_skin_does_not_freeze_whole_limb(self):
        im=image();im[:,:,:3]=[180,130,110]
        self.assertEqual(clothing_edges(model(),{'map':im})['faces'],[])

    def test_head_and_torso_are_outside_this_clothing_guard(self):
        for name in ('atama','mune'):
            m=model();m['bones'][1]['name']=name
            self.assertEqual(clothing_edges(m,{'map':image()})['faces'],[])

    def test_transparent_padding_does_not_become_an_opaque_clothing_border(self):
        im=image();im[:,:16,3]=0
        self.assertEqual(clothing_edges(model(),{'map':im})['faces'],[])

    def test_authored_repeat_uvs_and_reordered_records_retain_the_same_faces(self):
        m=model()
        for mesh in m['meshes']:
            for v in mesh['vertices']:v['uv']=[x+1 for x in v['uv']]
            mesh['vertices'].reverse()
            for mat in mesh['materials']:mat['triangles']=[[3-i for i in t] for t in mat['triangles']]
        self.assertEqual(clothing_edges(m,{'map':image()})['faces'],[[0,0,0,0],[1,0,0,1]])

    def test_source_model_and_pixels_are_immutable_and_bad_images_rejected(self):
        m=model();im=image();old=copy.deepcopy(m);pixels=im.copy()
        clothing_edges(m,{'map':im})
        self.assertEqual(m,old);np.testing.assert_array_equal(im,pixels)
        with self.assertRaises(ValueError):clothing_edges(m,{'map':im[:,:,:3]})
        m['meshes'][0]['vertices'][0]['uv'][0]=float('nan')
        with self.assertRaises(ValueError):clothing_edges(m,{'map':im})

    def test_worker_freezes_both_faces_without_guarding_unrelated_skin(self):
        from desktop.geometry_worker import select_guards
        m=model()
        self.assertFalse(any(row[4] for row in select_guards(m)))
        m['painted_clothing_edge_guards']=clothing_edges(m,{'map':image()})
        selected=[list(row[:4]) for row in select_guards(m) if row[4]]
        self.assertEqual(selected,[[0,0,0,0],[1,0,0,1]])

    def test_repeated_texture_strips_have_independent_face_guards(self):
        from desktop.geometry_worker import select_guards
        m=model();mesh=m['meshes'][0]
        mesh['materials']=[dict(texture_id=0,triangles=[[0,1,2]]),dict(texture_id=0,triangles=[[0,2,3]])]
        m['painted_clothing_edge_guards']=clothing_edges(m,{'map':image()})
        rows=select_guards(m)
        self.assertTrue(rows[0][4]);self.assertFalse(rows[1][4])
        self.assertEqual(rows[0][:4],(0,0,0,0));self.assertEqual(rows[1][:4],(0,1,0,0))


if __name__=='__main__':unittest.main()
