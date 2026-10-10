import json
from pathlib import Path
import tempfile
import unittest

from desktop.budget import SizeFitReport
from tools.generate_conformance_fixtures import vectors
from tools.pac_inspect import inspect_pac
from tools.pac_repack import replace_sections


class SizeFitTests(unittest.TestCase):
    def test_failed_fit_reports_smallest_attempt_and_all_stored_bytes(self):
        fixtures = vectors()
        base = fixtures['psp-quad.pac']
        large = replace_sections(base, {2: fixtures['psp-quad.yobj']+bytes(6000)})
        small = replace_sections(base, {2: fixtures['psp-quad.yobj']+bytes(3000)})
        with tempfile.TemporaryDirectory() as folder:
            report = SizeFitReport(Path(folder)/'size-fit.json', 2048,
                                   {'source.pac': 'source-hash'}, {'triangles': 2})
            report.record(large, texture_cap=64)
            report.record(small, texture_cap=32)
            # The last candidate need not be the smallest. Failures must report
            # the actual best attempt rather than whichever loop ran last.
            report.record(large, texture_cap=16)
            report.finish(False)
            saved = json.loads(report.path.read_text())
            best = saved['smallest_attempt']
            self.assertEqual(saved['status'], 'budget_exceeded')
            self.assertEqual(best['pac_bytes'], len(small))
            self.assertEqual(saved['over_budget_bytes'], len(small)-2048)
            self.assertEqual(best['texture_cap'], 32)
            keys = ('model_stored_bytes', 'textures_stored_bytes',
                    'retained_base_stored_bytes', 'headers_and_padding_bytes')
            self.assertEqual(sum(best[k] for k in keys), len(small))
            self.assertEqual(best['model_stored_bytes'], inspect_pac(small)['sections'][0]['size'])
            self.assertIn(f'{len(small):,} bytes', str(report.error()))
            self.assertIn(str(report.path), str(report.error()))
            self.assertEqual(len(saved['attempts']), 3)
            self.assertEqual(saved['inputs'], {'source.pac': 'source-hash'})
            self.assertFalse(list(Path(folder).glob('*.pac')))
            self.assertFalse(report.path.with_suffix('.tmp').exists())

    def test_size_fit_is_not_claimed_as_successful_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            report = SizeFitReport(Path(folder)/'size-fit.json', 148000, {}, {})
            report.record(vectors()['psp-quad.pac'])
            report.finish(True)
            saved = json.loads(report.path.read_text())
            self.assertEqual(saved['status'], 'size_fitted_pending_validation')
            self.assertEqual(saved['over_budget_bytes'], 0)
            self.assertEqual(saved['effective_aligned_maximum_bytes'], 147456)


if __name__ == '__main__':
    unittest.main()
