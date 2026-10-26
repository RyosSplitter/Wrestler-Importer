"""Shared waist cuts, persisted settings, legacy recipes and display-only guides."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from model_creator.core import PARTS, assemble, build, create_project, load_source, preview, qa, read_project
from model_creator.fixtures import pair
from model_creator.parts import DEFAULT_WAIST, LEGACY_WAIST, cut_planes, extract


class CreatorWaistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets=pair()

    def sources(self,root):
        paths=[]
        for i,data in enumerate(self.assets):
            path=root/f'Donor-{i}.pac';path.write_bytes(data);paths.append(path)
        return paths,[load_source(path) for path in paths]

    def test_default_is_above_old_cut_at_the_waistband(self):
        self.assertLess(DEFAULT_WAIST,LEGACY_WAIST)
        self.assertEqual(cut_planes()['waist'],(1,DEFAULT_WAIST))

    def test_adjusted_torso_and_legs_share_exact_cut_plane(self):
        with tempfile.TemporaryDirectory() as temp:
            _,sources=self.sources(Path(temp));model=sources[0]['model']
            names=[b['name'] for b in model['bones']]
            for height in (-3.,DEFAULT_WAIST,LEGACY_WAIST):
                planes=cut_planes(height)
                torso=extract(model,'Torso',names,planes=planes)
                legs=extract(model,'Legs',names,planes=planes)
                a=np.array([v['p'] for r in torso for v in r['poly']])
                b=np.array([v['p'] for r in legs for v in r['poly']])
                self.assertAlmostEqual(a[:,1].max(),height)
                self.assertAlmostEqual(b[:,1].min(),height)

    def test_configured_seams_pass_readback_and_pose_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            _,sources=self.sources(Path(temp))
            for height in (-2.75,-1.8):
                raw,_,report=assemble(sources,dict(Head=0,Torso=0,Arms=0,Legs=1),waist_y=height)
                self.assertEqual(report['waist_y'],height)
                seam=next(row for row in report['seams'] if row['joint']=='waist')
                self.assertEqual(seam['limit'],height)
                self.assertTrue(all(row['shared_seam_maximum_gap']<1e-5 for row in qa(raw,report)['poses'].values()))
            self.assertEqual(cut_planes()['waist'][1],DEFAULT_WAIST)

    def test_saved_custom_height_controls_export_and_legacy_recipe_keeps_its_cut(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths,_=self.sources(root)
            project=create_project(*paths,root/'Project')
            data=json.loads(Path(project).read_text());self.assertEqual(data['waist_y'],DEFAULT_WAIST)
            data['waist_y']=-2.65;Path(project).write_text(json.dumps(data))
            report=build(project,dict(Head=0,Torso=0,Arms=0,Legs=1),root/'Build',resolution=32)
            self.assertEqual(report['waist_y'],-2.65)
            data.pop('waist_y');Path(project).write_text(json.dumps(data))
            restored,_=read_project(project);self.assertEqual(restored['waist_y'],LEGACY_WAIST)

    def test_library_project_also_preserves_custom_and_legacy_waists(self):
        from model_creator.library import create_project as snapshot,read_project as read
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths,_=self.sources(root)
            sources=[load_source(path,library=True) for path in paths]
            path=snapshot(sources,dict.fromkeys(PARTS,0),root/'Library')
            data,_=read(path);self.assertEqual(data['waist_y'],DEFAULT_WAIST)
            data['waist_y']=-2.8;path.write_text(json.dumps(data));self.assertEqual(read(path)[0]['waist_y'],-2.8)
            data.pop('waist_y');path.write_text(json.dumps(data));self.assertEqual(read(path)[0]['waist_y'],LEGACY_WAIST)

    def test_cut_validation_rejects_bad_recipe_values_even_for_whole_donor(self):
        with tempfile.TemporaryDirectory() as temp:
            _,sources=self.sources(Path(temp))
            for value in (True,'-2.2',float('nan'),float('inf'),-9,0):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    assemble(sources,dict.fromkeys(PARTS,0),waist_y=value)

    def test_cut_guide_moves_without_altering_the_model_or_textures(self):
        with tempfile.TemporaryDirectory() as temp:
            _,sources=self.sources(Path(temp));source=sources[0];model=source['model']
            textures={n:source['textures'][n.casefold()] for n in model['texture_names']}
            old=copy.deepcopy(model)
            plain=preview(model,textures,'front',128)
            upper=preview(model,textures,'front',128,waist_guide=DEFAULT_WAIST)
            lower=preview(model,textures,'front',128,waist_guide=LEGACY_WAIST)
            self.assertNotEqual(upper.tobytes(),lower.tobytes())
            self.assertNotEqual(plain.tobytes(),upper.tobytes())
            self.assertEqual(model,old)
            for height in (-3.,-1.5):
                raw,original_textures,report=assemble(sources,dict.fromkeys(PARTS,0),waist_y=height)
                self.assertEqual(raw,source['sections'][2]);self.assertTrue(report['geometry_unchanged'])


if __name__=='__main__':
    unittest.main()
