"""Asset-free native array, library identity and generalized creator regressions."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from model_creator.core import PARTS, assemble, build, load_source, qa
from model_creator.fixtures import pair
from model_creator.library import Library, create_project, read_project
from model_creator.native import audit_yobj, restore_descriptors, allocation_fill
from tools.psp_mesh_audit import audit_yobj as ordinary_audit
from tools.psp_mesh_merge import write_model
from tools.pac_repack import replace_sections
from tools.psp_mesh_merge_trial import sections


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.assets=pair()

    def source(self,root,i=0):
        path=root/f'Synthetic-{i}.pac';path.write_bytes(self.assets[i%2]);return load_source(path,library=True)

    def test_descriptor_array_retains_buffers_and_validates_allocations(self):
        raw=next(r for s,r in sections(self.assets[0]) if s['id']==2)
        m=ordinary_audit(raw);second=copy.deepcopy(m['meshes'][0]);second['index']=1;m['meshes'].append(second)
        raw=write_model(m,[[0],[1]]);record=ordinary_audit(raw)['model_descriptor_raw']
        other=bytearray(record);other[:16]=b'hair'.ljust(16,b'\0')
        # Native multi-array pattern is [1,0,mesh-count,0].
        a=bytearray(record);struct.pack_into('<4I',a,16,1,0,1,0);struct.pack_into('<4I',other,16,1,0,1,0)
        result=restore_descriptors(raw,[a,other],[1,1]);decoded=audit_yobj(result)
        self.assertEqual(decoded['descriptor_owners'],[0,1])
        for before,after in zip(ordinary_audit(raw)['meshes'],decoded['meshes']):self.assertEqual(before['raw_vertices'],after['raw_vertices'])
        bad=bytearray(result);start=8+struct.unpack_from('<I',bad,48)[0];struct.pack_into('<I',bad,start+56,2)
        with self.assertRaisesRegex(ValueError,'partition'):audit_yobj(bad)
        # Extending the descriptor allocation backwards into a vertex buffer
        # cannot be accepted merely because its first count happens to match.
        bad=bytearray(result);struct.pack_into('<I',bad,48,8)
        with self.assertRaises(ValueError):audit_yobj(bad)

    def test_library_snapshots_independent_of_original_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);s=[self.source(root,i) for i in range(3)]
            choices=dict(Head=2,Torso=0,Arms=1,Legs=0);project=create_project(s,choices,root/'Project')
            for row in s:Path(row['path']).unlink()
            metadata,loaded=read_project(project);self.assertEqual(len(loaded),3);self.assertEqual(metadata['selections'],choices)
            raw,textures,report=assemble(loaded,choices,library=True);qa(raw,report,library=True)
            self.assertGreater(report['interior_source_records_verified'],0)

    def test_facial_bind_variants_are_preserved_with_different_bone_sets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sources=[self.source(root,i) for i in (0,1)]
            m=sources[1]['model'];extra=bytearray(m['bone_raw'][:80]);extra[:16]=b'UnusedHelper'.ljust(16,b'\0')
            m['bone_raw']+=extra;h=bytearray(m['header']);struct.pack_into('<I',h,28,len(m['bones'])+1);m['header']=bytes(h)
            # Serialize/read to exercise different native bone tables, not a
            # model dictionary which disagrees with its underlying bytes.
            raw=write_model(m,[[i] for i in range(len(m['meshes']))]);path=root/'Extra.pac'
            path.write_bytes(replace_sections(sources[1]['data'],{2:raw}));sources[1]=load_source(path,library=True)
            raw,_,r=assemble(sources,dict(Head=1,Torso=0,Arms=0,Legs=0),library=True)
            decoded=audit_yobj(raw);self.assertIn('UnusedHelper',[b['name'] for b in decoded['bones']])
            expected=next(b for b in sources[1]['model']['bones'] if b['name']=='atama')
            self.assertEqual(next(b for b in decoded['bones'] if b['name']=='atama')['local_position'],expected['local_position'])
            self.assertTrue(all(p['passed'] for p in r['interior_pose_comparison'].values()))

    def test_unchanged_source_is_exact_and_budget_is_still_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);project=create_project([self.source(root)],dict.fromkeys(PARTS,0),root/'Project')
            r=build(project,dict.fromkeys(PARTS,0),root/'Build',resolution=64,library=True)
            self.assertEqual((root/'Build/created-model.pac').read_bytes(),self.assets[0])
            with patch('model_creator.core.MAX_BYTES',1):
                with self.assertRaisesRegex(ValueError,'exceeding'):build(project,dict.fromkeys(PARTS,0),root/'No',resolution=64,library=True)
            self.assertFalse((root/'No').exists())

    def test_snapshot_path_and_hash_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);project=create_project([self.source(root)],dict.fromkeys(PARTS,0),root/'Project')
            metadata=json.loads(project.read_text());metadata['sources'][0]['file']='../Synthetic-0.pac';project.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'snapshot path'):read_project(project)

    def test_prepared_library_refuses_changed_asset_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);s=self.source(root)
            catalog=dict(schema='psp-model-creator.library/1',models=[dict(label='Synthetic',file=Path(s['path']).name,sha256=s['sha256'])])
            (root/'catalog.json').write_text(json.dumps(catalog));lib=Library(root)
            self.assertEqual(lib.source(0)['sha256'],s['sha256'])
            Path(s['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed'):lib.source(0)
            catalog['models'][0]['file']='../outside.pac';(root/'catalog.json').write_text(json.dumps(catalog))
            with self.assertRaisesRegex(ValueError,'path'):Library(root)

    def test_unknown_nonzero_gap_not_silently_discarded(self):
        from tools.generate_conformance_fixtures import vectors
        raw=bytearray(vectors()['psp-quad.yobj']);raw[160:168]=b'UNKNOWN!'
        with self.assertRaisesRegex(ValueError,'Unclassified'):allocation_fill(bytes(raw),audit_yobj(bytes(raw)))
