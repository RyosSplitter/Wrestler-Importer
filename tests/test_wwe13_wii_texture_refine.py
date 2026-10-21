"""Procedural quality/budget candidate checks; no game-derived fixtures."""
import copy,unittest
import numpy as np
from tools.wwe13_wii_texture_refine import candidates
from desktop.texture_optimizer.candidates import read_gim


def model(name='root'):
    return dict(bones=[dict(index=0,name=name,parent=-1)],textures=['sample'],meshes=[dict(bone_palette=[0],
        vertices=[dict(position=p,uv=uv,weights=[1.])for p,uv in zip([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],[[0.,0.],[1.,0.],[0.,1.]])],
        materials=[dict(texture_id=0,triangles=[[0,1,2]])])])


class TextureRefinementTests(unittest.TestCase):
    def test_palette_exploration_is_independent_and_source_bounded(self):
        y,x=np.indices((32,32));source=np.zeros((32,32,4),np.uint8);source[:,:,:3]=np.stack([x*7,y*7,(x+y)*3],axis=2);source[:,:,3]=255
        m=model();before=copy.deepcopy(m);im=source.copy()
        _,_,report=candidates(m,[source],[dict(bits=8,cutout=False)],progress=lambda *a,**k:None)
        caps={r['requested_useful_colors']for r in report[0]['candidates']}
        self.assertTrue({16,32,64,128,256}.issubset(caps))
        self.assertTrue(all((r['width'],r['height'])==(32,32)and r['bits']==8 for r in report[0]['candidates']))
        self.assertEqual(m,before);np.testing.assert_array_equal(source,im)
    def test_iris_keeps_resolution_and_color_floor(self):
        y,x=np.indices((64,32));source=np.stack([x*7,y*3,x+y,np.full_like(x,255)],axis=2).astype(np.uint8)
        _,_,report=candidates(model('l_eye'),[source],[dict(bits=8,cutout=False)],progress=lambda *a,**k:None)
        self.assertTrue(report[0]['ocular_surface'])
        self.assertTrue(all((r['width'],r['height'])==(32,64) and r['requested_useful_colors']>=64 for r in report[0]['candidates']))
    def test_fractional_alpha_and_source_color_ceiling(self):
        source=np.zeros((64,32,4),np.uint8);source[:24]=[120,70,40,73];source[24:48]=[70,40,20,255]
        rows,_,_=candidates(model(),[source],[dict(bits=8,cutout=True)],progress=lambda *a,**k:None)
        for row in rows[0]:
            ix,pal=read_gim(row['raw']);rgba=pal[ix]
            self.assertLessEqual(len(np.unique(rgba.reshape(-1,4),axis=0)),3)
            self.assertTrue(set(np.unique(rgba[:,:,3])).issubset({0,73,255}))
            if rgba.shape==source.shape:np.testing.assert_array_equal(rgba[:,:,3],source[:,:,3])


if __name__=='__main__':unittest.main()
