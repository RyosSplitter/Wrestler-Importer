"""Real bundled bind-branch regressions and asset-free texture-option contracts."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_creator.core import PARTS, assemble, build, load_source, qa
from model_creator.fixtures import pair
from model_creator.library import Library, create_project
from model_creator.textures import fit_textures
from tools.psp_mesh_merge_trial import sections


class Creator030Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library=Library();cls.models={entry['label']:cls.library.source(i) for i,entry in enumerate(cls.library.entries)}

    def test_hardy_and_jbl_parts_preserve_source_records_under_both_pose_conventions(self):
        for label in ('Jeff-Hardy','Matt-Hardy','JBL(Suit)'):
            for part in PARTS:
                with self.subTest(donor=label,part=part):
                    selections=dict.fromkeys(PARTS,0);selections[part]=1
                    raw,textures,report=assemble([self.models['Batista'],self.models[label]],selections,library=True)
                    result=qa(raw,report,library=True)
                    self.assertTrue(report['readback_attributes_and_topology'])
                    self.assertEqual(len(result['local_axis_poses']),10)
                    for checks in (report['interior_pose_comparison'],report['local_axis_interior_pose_comparison']):
                        self.assertEqual(len(checks),10)
                        self.assertTrue(all(c['maximum_source_position_difference']<=.03 for c in checks.values()))

    def test_conflicting_body_hierarchy_still_rejected(self):
        import copy
        a=self.models['Batista'];b=copy.deepcopy(self.models['JBL(Suit)'])
        next(x for x in b['model']['bones'] if x['name']=='l_momo')['parent']=-1
        with self.assertRaisesRegex(ValueError,'hierarchy'):assemble([a,b],dict(Head=0,Torso=0,Arms=0,Legs=1),library=True)

    def test_native_selected_head_pivot_is_kept_when_it_already_passes(self):
        raw,_,report=assemble([self.models['Batista'],self.models['Jeff-Hardy']],dict(Head=1,Torso=0,Arms=0,Legs=0),library=True)
        self.assertFalse(report['shared_neck_fit']['applied'])
        self.assertTrue(report['local_axis_interior_pose_comparison']['neck']['passed'])

    def test_shared_neck_solver_improves_actual_limiting_local_axis_case_without_weight_edits(self):
        raw,_,report=assemble([self.models['Batista'],self.models['Jeff-Hardy']],dict(Head=0,Torso=1,Arms=0,Legs=0),library=True)
        fit=report['shared_neck_fit'];self.assertTrue(fit['applied'])
        self.assertGreater(fit['head_endpoint_error'],.03);self.assertLess(fit['predicted_worst_pose_error'],.03)
        self.assertGreater(fit['torso_fraction'],0);self.assertLess(fit['torso_fraction'],1)
        self.assertTrue(report['readback_attributes_and_topology'])

    def test_maximum_texture_option_does_not_change_an_already_fitting_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'Synthetic.pac';path.write_bytes(pair()[0]);source=load_source(path,library=True)
            project=create_project([source],dict.fromkeys(PARTS,0),root/'Project')
            a=build(project,dict.fromkeys(PARTS,0),root/'Off',resolution=64,library=True,allow_oversize=True)
            b=build(project,dict.fromkeys(PARTS,0),root/'On',resolution=64,library=True,allow_oversize=True,maximum_textures=True)
            self.assertEqual((root/'Off/created-model.pac').read_bytes(),(root/'On/created-model.pac').read_bytes())
            self.assertEqual(b['maximum_texture_downgrade']['changed_textures'],0);self.assertTrue(b['textures_byte_exact'])

    def test_impossible_texture_fit_stays_exportable_with_warning_and_unchanged_non_texture_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'Synthetic.pac';data=pair()[0];path.write_bytes(data)
            project=create_project([load_source(path,library=True)],dict.fromkeys(PARTS,0),root/'Project')
            with patch('model_creator.core.MAX_BYTES',1):
                result=build(project,dict.fromkeys(PARTS,0),root/'Build',resolution=64,library=True,allow_oversize=True,maximum_textures=True)
            self.assertFalse(result['within_budget']);self.assertTrue(result['budget_warning']);self.assertTrue((root/'Build/created-model.pac').is_file())
            before={s['id']:(s['sha256'],r) for s,r in sections(data)}
            after={s['id']:(s['sha256'],r) for s,r in sections((root/'Build/created-model.pac').read_bytes())}
            for section in before:
                if section!=9:self.assertEqual(before[section],after[section])
