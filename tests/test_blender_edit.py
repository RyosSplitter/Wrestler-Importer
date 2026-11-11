import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np
from PIL import Image

from model_creator.morph.fixtures import donor
from model_creator.core import load_source
from model_creator.blender_edit.bridge import make_job,apply_result,create_session,import_session,session_source

class BlenderEditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.pac=self.root/'source.pac';self.pac.write_bytes(donor());self.source=load_source(self.pac);self.job=make_job(self.source)

    def result(self):
        rows=[]
        for mesh in self.job['meshes']:
            rows.append({out:[v[key]for v in mesh['vertices']]for out,key in [('positions','position'),('normals','normal'),('uv','uv')]})
        paths=[]
        from desktop.texture_optimizer.candidates import read_gim
        for i,t in enumerate(self.job['textures']):
            ix,pal=read_gim(self.source['textures'][t['name'].casefold()]);path=self.root/f'{i}.png';Image.fromarray(pal[ix]).save(path);paths.append(path)
        return dict(baseline_sha256=self.source['sha256'],meshes=rows),paths

    def test_noop_is_exact_and_invalid_geometry_is_rejected(self):
        result,paths=self.result();pac,proof=apply_result(self.source,result,paths,dict(seams=[]));self.assertEqual(pac,self.pac.read_bytes())
        bad=copy.deepcopy(result);bad['meshes'][0]['positions'][0]=[float('nan'),0,0]
        with self.assertRaisesRegex(ValueError,'Invalid Blender'):apply_result(self.source,bad,paths,dict(seams=[]))
        bad=copy.deepcopy(result);bad['meshes'][0]['positions']=[[0,0,0]for _ in bad['meshes'][0]['positions']]
        with self.assertRaisesRegex(ValueError,'collapses|reverses'):apply_result(self.source,bad,paths,dict(seams=[]))

    def test_uv_and_texture_edit_preserve_native_rig(self):
        result,paths=self.result()
        for row in result['meshes']:
            row['uv']=[[u+.025,v]for u,v in row['uv']]
        im=Image.open(paths[0]).convert('RGBA');a=np.array(im);a[:,:,:3]=[80,100,160];Image.fromarray(a).save(paths[0])
        pac,proof=apply_result(self.source,result,paths,dict(seams=[]));p=self.root/'edited.pac';p.write_bytes(pac);edited=load_source(p)
        self.assertEqual(edited['model']['bone_raw'],self.source['model']['bone_raw']);self.assertTrue(proof['changed_textures'])
        for a,b in zip(self.source['model']['meshes'],edited['model']['meshes']):
            self.assertEqual(a['bone_palette'],b['bone_palette'])
            for x,y in zip(a['vertices'],b['vertices']):self.assertEqual(x['weights'],y['weights']);self.assertEqual(x['position'],y['position'])

    def test_budget_failure_is_explicit(self):
        from unittest.mock import patch
        result,paths=self.result()
        with patch('model_creator.blender_edit.bridge.MAX_BYTES',1):
            with self.assertRaisesRegex(ValueError,'exceed the PSP PAC budget'):apply_result(self.source,result,paths,dict(seams=[]))

    def test_render_failure_never_publishes_partial_build(self):
        from unittest.mock import patch
        result,paths=self.result();blend=self.root/'model.blend';blend.write_bytes(b'fixture')
        def worker(mode,job,output,**kwargs):
            for i,path in enumerate(paths):shutil.copy2(path,output.parent/f'texture_{i:03d}.png')
            return result
        with patch('model_creator.blender_edit.bridge.session_source',return_value=(dict(library=False),self.source)),patch('model_creator.blender_edit.bridge.run_worker',side_effect=worker),patch('model_creator.blender_edit.bridge.preview',side_effect=RuntimeError('preview failed')):
            with self.assertRaisesRegex(RuntimeError,'preview failed'):import_session(self.root,blend,self.pac,self.root/'partial')
        self.assertFalse((self.root/'partial').exists());self.assertEqual(self.pac.read_bytes(),self.source['data'])

    @unittest.skipUnless(shutil.which('blender'),'Blender integration runtime unavailable')
    def test_actual_blender_roundtrip_edits_and_rejections(self):
        folder=self.root/'session';blend=create_session(self.pac,folder,runtime=shutil.which('blender'))
        shutil.copy2(blend,folder/'clean.blend')
        noop,_,_=import_session(folder,blend,self.pac,self.root/'noop',runtime=shutil.which('blender'))
        self.assertEqual((noop/'created-model.pac').read_bytes(),self.pac.read_bytes())
        self.pac.write_bytes(self.source['data']+b'changed')
        with self.assertRaisesRegex(ValueError,'baseline differs'):session_source(folder,self.pac)
        self.pac.write_bytes(self.source['data'])
        script=self.root/'edit.py';script.write_text("""import bpy
from pathlib import Path
rig=bpy.data.objects['PSP Rig']
for obj in bpy.context.scene.objects:
 if obj.type=='MESH':
  for v in obj.data.vertices:v.co*=1.01
  for uv in obj.data.uv_layers[0].data:uv.uv.x+=.02
image=bpy.data.images['PSP Image 000'];pixels=list(image.pixels)
for i in range(0,len(pixels),4):pixels[i:i+3]=[.15,.35,.8]
image.pixels.foreach_set(pixels);image.pack()
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
""")
        subprocess.run([shutil.which('blender'),'-b',str(blend),'--disable-autoexec','--python-exit-code','1','--python',str(script)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
        output,report,source=import_session(folder,blend,self.pac,self.root/'edited',runtime=shutil.which('blender'))
        self.assertNotEqual(source['data'],self.pac.read_bytes());self.assertIn('blender_edit',report);self.assertTrue(report['blender_edit']['changed_textures'])
        for before,after in zip(self.source['model']['meshes'],source['model']['meshes']):
            for a,b in zip(before['vertices'],after['vertices']):
                self.assertTrue(np.allclose(a['normal'],b['normal'],atol=1e-5),'Uniform scaling changed the original normal field')
                self.assertAlmostEqual(b['uv'][0]-a['uv'][0],.02,places=5)
        # Modifying the source weights is rejected inside Blender before native patching.
        script.write_text("import bpy\no=next(o for o in bpy.context.scene.objects if o.type=='MESH')\no.vertex_groups[0].add([0],.4,'REPLACE')\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
        subprocess.run([shutil.which('blender'),'-b',str(blend),'--disable-autoexec','--python-exit-code','1','--python',str(script)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
        with self.assertRaisesRegex(ValueError,'Skin weights changed'):import_session(folder,blend,self.pac,self.root/'rejected',runtime=shutil.which('blender'))
        self.assertFalse((self.root/'rejected').exists())
        script.write_text("""import bpy,json,sys
from pathlib import Path
sys.path.insert(0,ROOT)
from model_creator.blender_edit.worker import extract
folder=Path(FOLDER);job=json.loads((folder/'job.json').read_text());contract=json.loads((folder/'contract.json').read_text())
cases={
 'ids':"o.data.attributes['psp_record_id'].data[0].value=1",
 'modifier':"o.modifiers.new('Unexpected','DECIMATE')",
 'rig':"bpy.data.objects['PSP Rig'].location.x=1",
 'extra mesh':"bpy.context.collection.objects.link(o.copy())",
 'uv split':"v=next(v.index for v in o.data.vertices if sum(l.vertex_index==v.index for l in o.data.loops)>1); li=next(l.index for l in o.data.loops if l.vertex_index==v); o.data.uv_layers[0].data[li].uv.x+=.1",
 'shader':"o.data.materials[0].node_tree.nodes['Shader'].inputs['Roughness'].default_value=.1",
 'material':"o.data.materials.append(o.data.materials[0]);o.data.polygons[0].material_index=1",
}
for name,code in cases.items():
 bpy.ops.wm.open_mainfile(filepath=str(folder/'clean.blend'),use_scripts=False)
 o=next(o for o in bpy.context.scene.objects if o.type=='MESH');exec(code)
 target=folder/'rejected-case.blend';bpy.ops.wm.save_as_mainfile(filepath=str(target))
 try:extract(job,contract,target,folder)
 except ValueError:pass
 else:raise AssertionError('Accepted unsupported edit: '+name)
""".replace('ROOT',repr(str(Path(__file__).resolve().parents[1]))).replace('FOLDER',repr(str(folder))))
        completed=subprocess.run([shutil.which('blender'),'-b','--disable-autoexec','--python-exit-code','1','--python',str(script)],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stdout[-4000:]+completed.stderr[-1000:])

if __name__=='__main__':unittest.main()
