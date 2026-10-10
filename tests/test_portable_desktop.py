import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from desktop.adapters import adapter,FORMATS
from desktop.core import palette_rgba,validate_pac,Request,Cancelled,run_job
from desktop.native import serialize
from desktop.geometry_worker import select_guards
from desktop.preview import render
from desktop.storage import save_as
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.generate_conformance_fixtures import vectors

class PortableTests(unittest.TestCase):
    def test_disabled_formats_are_not_aliases(self):
        self.assertEqual([f.key for f in FORMATS if f.supported],['hctp'])
        for key in ('jbi','sym','svr','unknown'):
            with self.assertRaises(ValueError):adapter(key)

    def test_native_writer_round_trip_and_triangle_orientation(self):
        base=audit_yobj(vectors()['psp-quad.yobj'])
        mesh=copy.deepcopy(base['meshes'][0]);mesh['target_part']=0
        prepared=dict(meshes=[mesh],textures=['skin'])
        raw=serialize(prepared,base,[dict(bits=4,cutout=False)])
        actual=audit_yobj(raw)
        self.assertEqual(actual['bone_raw'],base['bone_raw'])
        self.assertEqual(actual['meshes'][0]['bone_palette'],[0,1])
        self.assertEqual(actual['meshes'][0]['vertices'],base['meshes'][0]['vertices'])
        self.assertEqual(actual['meshes'][0]['materials'][0]['triangles'],mesh['materials'][0]['triangles'])

    def test_exact_cutout_palette(self):
        rgba=np.array([[[10,20,30,0],[10,20,30,127],[10,20,30,255]]],dtype=np.uint8)
        p,c=palette_rgba(rgba);np.testing.assert_array_equal(c[p],rgba)

    def test_preview_uses_final_texture_and_view(self):
        files=vectors();m=audit_yobj(files['psp-quad.yobj'])
        image=np.asarray(render(m,{'skin':files['skin-t4.gim']},'front',96))
        self.assertGreater(np.count_nonzero(image[:,:,0]>image[:,:,1]+15),10)

    def test_export_rejects_modified_candidate_and_input_overwrite(self):
        files=vectors()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);candidate=root/'candidate.pac';candidate.write_bytes(files['psp-quad.pac']);source=root/'source.pac';source.write_bytes(b'source');base=root/'base.pac';base.write_bytes(b'base')
            from desktop.core import digest
            result=dict(pac=str(candidate),source=str(source),base=str(base),sha256=digest(candidate))
            for p in (source,base,candidate):
                with self.assertRaises(ValueError):save_as(result,p)
            output=root/'export.pac';save_as(result,output);self.assertEqual(output.read_bytes(),candidate.read_bytes())
            candidate.write_bytes(candidate.read_bytes()+b'x')
            with self.assertRaises(ValueError):save_as(result,output)

    def test_early_cancellation_does_not_touch_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'a.pac';b=root/'b.pac';a.write_bytes(b'unchanged');b.write_bytes(b'base')
            with self.assertRaises(Cancelled):run_job(Request(str(a),str(b)),root/'job',cancel=lambda:True)
            self.assertEqual(a.read_bytes(),b'unchanged');self.assertEqual(b.read_bytes(),b'base')

    def test_final_pac_audit_and_size(self):
        files=vectors();model,gims=validate_pac(files['psp-quad.pac']);self.assertEqual(model['report']['triangles'],2)
        with self.assertRaises(ValueError):validate_pac(files['psp-quad.pac'],max_bytes=100)

    def test_torso_guard_has_no_character_selector(self):
        model=dict(bones=[dict(index=0,name='koshi',parent=-1)],meshes=[dict(index=0,bone_palette=[0],vertices=[dict(position=p,weights=[1.]) for p in ((0,0,0),(1,0,0),(0,1,0))],materials=[dict(texture_id=0,triangles=[[0,1,2]])])])
        self.assertEqual(select_guards(model),[(0,0,0,True)])

    def test_selective_eye_policy_preserves_source_jaw_records(self):
        import zipfile
        from desktop.core import prepare,base_model
        from model_qa.geometry import geometry
        root=Path(__file__).resolve().parents[1]
        with zipfile.ZipFile(root/'downloads/Jericho-QA-facial-weights-experiment.zip') as z:source=json.loads(z.read('trial/input-source-weighted.json'))
        _,target=base_model(root/'assets/Kurt-Angle-Ring.PAC');candidate,legacy,jaw=prepare(source,target)
        a,b,c=map(geometry,(candidate,legacy,jaw))
        eye=[i for i,n in enumerate(c.bone_names) if n in ('l_eye','r_eye','l_mabuta','r_mabuta')]
        selected=c.weights[:,eye].sum(1)>1e-7
        self.assertGreater(selected.sum(),0)
        np.testing.assert_array_equal(a.weights[selected],b.weights[selected])
        np.testing.assert_array_equal(a.weights[~selected],c.weights[~selected])
        jaw_ids=[i for i,n in enumerate(c.bone_names) if n=='d_kuchi' or n.startswith('d_kuchi_')]
        mask=c.weights[:,jaw_ids].sum(1)>1e-7
        self.assertGreater(mask.sum(),0);np.testing.assert_array_equal(a.weights[mask],c.weights[mask])

    def test_modified_source_container_keeps_surface_and_weights(self):
        from tools.hctp_weights import read_hctp_with_weights
        from tools.portable_fixture import create
        source=read_hctp_with_weights(vectors()['hctp-quad.yobj'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'custom.pac';create(source,path);actual,textures=adapter('hctp').read(path)
            self.assertEqual(actual['triangle_count'],2)
            for a,b in zip(source['meshes'][0]['vertices'],actual['meshes'][0]['vertices']):
                np.testing.assert_array_equal(a['position'],b['position']);np.testing.assert_array_equal(a['weights'],b['weights'])

if __name__=='__main__':unittest.main()
