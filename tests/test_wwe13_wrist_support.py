"""Procedural Blender regression for mixed forearm/hand support at a wrist."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import numpy as np


@unittest.skipUnless(shutil.which('blender'), 'Blender unavailable')
class WristSupportTests(unittest.TestCase):
    def test_guarded_wrist_retains_source_surface_and_posed_positions(self):
        names=['root','l_sakotsu','l_kote','l_te','l_eye','r_eye']
        bones=[dict(index=i,name=n,parent=[-1,0,1,2,0,0][i]) for i,n in enumerate(names)]
        vertices=[dict(position=[x/3,y/3,0.],normal=[0.,0.,1.],uv=[x/3,y/3],
                       color=[255]*4,weights=[0.,0.,.6,.4,0.,0.]) for y in range(4) for x in range(4)]
        triangles=[]
        for y in range(3):
            for x in range(3):
                a=y*4+x;triangles += [[a,a+1,a+4],[a+1,a+5,a+4]]
        source=dict(bones=bones,bone_count=6,triangle_count=len(triangles),vertex_count=len(vertices),mesh_count=1,textures=['wrist'],meshes=[dict(index=0,role='Body',
                    bone_palette=list(range(6)),vertices=vertices,materials=[dict(texture_id=0,triangles=triangles)])])
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'source.json').write_text(json.dumps(source))
            (folder/'profile.json').write_text(json.dumps(dict(Arms=.35,Hands=1.,Head=1.,Torso=1.,Legs=1.,Eyes=1.,Mouth=1.,Hair=1.)))
            script=folder/'trial.py';script.write_text(
                'import sys\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(root))+')\n'
                'from tools.wwe13_reduce_trial import run\n'
                'p=Path('+repr(str(folder))+')\n'
                'run(p/"source.json",p/"baseline.json",p/"profile.json",material_only=True,export_face_floor=True)\n'
                'run(p/"source.json",p/"guarded.json",p/"profile.json",material_only=True,export_face_floor=True,preserve_hand_transitions=True)\n')
            env=os.environ.copy();env['BLENDER_USER_CONFIG']=str(folder/'config');env['BLENDER_USER_EXTENSIONS']=str(folder/'extensions')
            result=subprocess.run([shutil.which('blender'),'--background','--factory-startup','--python-exit-code','1',
                                   '--python',str(script)],cwd=root,env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            old=json.loads((folder/'baseline.json').read_text());new=json.loads((folder/'guarded.json').read_text())
            count=lambda m:sum(len(a['triangles'])for mesh in m['meshes']for a in mesh['materials'])
            self.assertLess(count(old),len(triangles));self.assertEqual(count(new),len(triangles))
            # An analytical world-z hand rotation must retain the source surface,
            # not merely a normalized weight sum after classification.
            angle=np.deg2rad(35);rotation=np.array([[np.cos(angle),-np.sin(angle),0.],
                                                  [np.sin(angle),np.cos(angle),0.],[0.,0.,1.]])
            def posed_key(v):
                p=np.array(v['position']);w=v['weights']
                return tuple(np.round(w[2]*p+w[3]*(rotation@p),6))
            expected={posed_key(v) for v in vertices}
            actual={posed_key(v) for m in new['meshes']for v in m['vertices']}
            self.assertEqual(expected,actual)


if __name__=='__main__':unittest.main()
