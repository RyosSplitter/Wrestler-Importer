"""Actual Blender regression for authored two-sided corner normals."""
import copy,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_wwe13_wii_corpus import model


@unittest.skipUnless(shutil.which('blender'),'Blender executable unavailable')
class BlenderNormalTests(unittest.TestCase):
    def test_source_corner_interpolation_preserves_both_sides(self):
        root=Path(__file__).resolve().parents[1];m=model('color');front=m['meshes'][0];front['region']='Torso'
        back=copy.deepcopy(front);back['index']=1;back['materials'][0]['triangles']=[[2,1,0]]
        for v in back['vertices']:v['normal']=[0.,0.,-1.]
        m.update(meshes=[front,back],mesh_count=2,bone_count=1,triangle_count=2,vertex_count=6,texture_count=1)
        with tempfile.TemporaryDirectory()as td:
            folder=Path(td);(folder/'in.json').write_text(json.dumps(m))
            script=folder/'probe.py';script.write_text(
                'import sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(root/'tools'))+')\n'
                'import blender_reduce\nblender_reduce.RATIOS["Torso"]=1.\n'
                'm=json.loads(Path('+repr(str(folder/'in.json'))+').read_text())\n'
                'try:\n blender_reduce.reduce(m,1.,regional=True)\nexcept ValueError as e:\n assert "Degenerate smoothing normal"in str(e)\nelse:\n raise AssertionError("Fixture did not reproduce cancellation")\n'
                'r=blender_reduce.reduce(m,1.,regional=True,export_face_floor=True,source_normals=True)\n'
                'Path('+repr(str(folder/'out.json'))+').write_text(json.dumps(r))\n')
            env=os.environ.copy();env['BLENDER_USER_CONFIG']=str(folder/'config')
            p=subprocess.run([shutil.which('blender'),'-b','-t','1','--python-exit-code','1','--python',str(script)],env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stdout[-2000:]+p.stderr[-2000:]);out=json.loads((folder/'out.json').read_text())
        self.assertEqual(out['triangle_count'],2)
        for i,mesh in enumerate(out['meshes']):
            expected=[0.,0.,1.]if i==0 else[0.,0.,-1.]
            for v in mesh['vertices']:self.assertEqual(v['normal'],expected)
            self.assertEqual({tuple(v['position'])for v in mesh['vertices']},{tuple(v['position'])for v in m['meshes'][i]['vertices']})


if __name__=='__main__':unittest.main()
