import copy,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from tools.wwe13_wii_preview import unlit_copy,render_unlit


class PreviewTests(unittest.TestCase):
    def test_unlit_matches_texture_color_and_never_mutates_model(self):
        model=dict(texture_names=['test'],meshes=[dict(vertices=[dict(position=p,normal=[0.,0.,-1.],uv=[.5,.5],color=[255]*4)for p in [[-1.,1.,-1.],[1.,1.,-1.],[0.,-1.,-1.]]],materials=[dict(texture_id=0,triangles=[[0,1,2]])])])
        before=copy.deepcopy(model);texture=np.zeros((32,32,4),np.uint8);texture[:]=[160,100,70,255]
        with tempfile.TemporaryDirectory()as td:
            path=Path(td)/'unlit.png';render_unlit(model,{'test':texture},'front',path)
            pixel=np.array(Image.open(path))[320,320].astype(int)
        self.assertTrue(np.max(np.abs(pixel-[160,100,70]))<=1)
        self.assertEqual(model,before)
        display=unlit_copy(model,'left')
        self.assertEqual([v['position']for v in display['meshes'][0]['vertices']],[v['position']for v in model['meshes'][0]['vertices']])


if __name__=='__main__':unittest.main()
