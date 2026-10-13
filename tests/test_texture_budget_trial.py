"""Asset-free checks for the explicit, isolated texture-budget experiment."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from experiments.texture_budget_trial import allocation, run
from tools.generate_conformance_fixtures import vectors
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from desktop.texture_optimizer.candidates import read_gim


class TextureBudgetTrialTests(unittest.TestCase):
    def fixture(self, folder):
        fixture = vectors()
        baseline = folder/'baseline.pac'
        source = folder/'source.pac'
        baseline.write_bytes(fixture['psp-quad.pac'])
        source.write_bytes(fixture['psp-quad.pac'])
        model = audit_yobj(fixture['psp-quad.yobj'])
        model['textures'] = model['texture_names']
        p, c = read_gim(fixture['skin-t4.gim'])
        rng = np.random.default_rng(14)
        rgba = c[rng.integers(0,16,(64,64))].copy()
        rgba[:,:,3] = 255
        decoded = [(0,'skin',b'',rgba,dict(format='synthetic'))]
        return source, baseline, model, decoded

    def test_frozen_model_source_ceiling_and_preview_materials(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, baseline, model, decoded = self.fixture(root)
            with patch('experiments.texture_budget_trial.adapter') as a:
                a.return_value.read.return_value = model, decoded
                report = run(source, baseline, root/'result', {'skin':(64,64)},
                             pixel_limit=12000, renders=False)
            self.assertTrue(report['non_texture_stored_and_decoded_payloads_exact'])
            before = {s['id']: raw for s,raw in sections(baseline.read_bytes())}
            after = {s['id']: raw for s,raw in sections((root/'result/candidate.pac').read_bytes())}
            self.assertEqual(before[2], after[2])
            self.assertIn('newmtl texture_0', (root/'result/preview/preview.mtl').read_text())
            self.assertIn('map_Kd skin.png', (root/'result/preview/preview.mtl').read_text())
            self.assertEqual(report['poses']['status'], 'pass')
            self.assertEqual(report['after_allocation'], allocation((root/'result/candidate.pac').read_bytes()))

    def test_pixel_limit_withholds_even_when_pac_fits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, baseline, model, decoded = self.fixture(root)
            with patch('experiments.texture_budget_trial.adapter') as a:
                a.return_value.read.return_value = model, decoded
                with self.assertRaisesRegex(ValueError,'exceeds'):
                    run(source, baseline, root/'result', {'skin':(64,64)}, pixel_limit=1, renders=False)
            self.assertFalse((root/'result/candidate.pac').exists())
            report = json.loads((root/'result/report.json').read_text())
            self.assertTrue(report['pac_budget_pass'])
            self.assertFalse(report['pixel_budget_pass'])

    def test_pac_limit_withholds_even_when_pixel_allocation_fits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, baseline, model, decoded = self.fixture(root)
            with patch('experiments.texture_budget_trial.adapter') as a:
                a.return_value.read.return_value = model, decoded
                with self.assertRaisesRegex(ValueError,'exceeds'):
                    run(source, baseline, root/'result', {'skin':(64,64)},
                        pixel_limit=12000, target=len(baseline.read_bytes()), renders=False)
            self.assertFalse((root/'result/candidate.pac').exists())
            report = json.loads((root/'result/report.json').read_text())
            self.assertFalse(report['pac_budget_pass'])
            self.assertTrue(report['pixel_budget_pass'])

    def test_upscaling_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, baseline, model, decoded = self.fixture(root)
            with patch('experiments.texture_budget_trial.adapter') as a:
                a.return_value.read.return_value = model, decoded
                with self.assertRaisesRegex(ValueError,'ceiling'):
                    run(source, baseline, root/'result', {'skin':(128,128)}, pixel_limit=12000, renders=False)
            self.assertFalse((root/'result/candidate.pac').exists())


if __name__ == '__main__':
    unittest.main()
