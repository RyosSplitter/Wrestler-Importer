import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.pipeline import BACKEND, Job, verify_backend
from app import settings
from app.worker import main as worker
from app.size_fit import next_ratio


class BetaTests(unittest.TestCase):
    def test_size_retry_reduces_only_the_uniform_ratio(self):
        ratio = next_ratio(0.3, 167936, 120000, 147456)
        self.assertGreaterEqual(ratio, 0.1)
        self.assertLess(ratio, 0.3)
        self.assertLess(120000 * ratio / 0.3 + 167936 - 120000, 147456)

    def test_size_retry_refuses_unavoidable_overhead_or_extreme_reduction(self):
        with self.assertRaisesRegex(ValueError, 'no model space'):
            next_ratio(0.3, 300000, 10000, 147456)
        with self.assertRaisesRegex(ValueError, 'quality floor'):
            next_ratio(0.1, 167936, 120000, 147456)

    def test_pinned_backend_rejects_a_changed_reducer(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = Path(folder) / 'backend'
            shutil.copytree(BACKEND, backend)
            profile = verify_backend(backend)
            self.assertEqual(profile['sample']['pac_bytes'], 147456)
            self.assertEqual(profile['weight_encoding'], 'float')
            with (backend / 'blender_reduce.py').open('a') as f:
                f.write('\n# edited\n')
            with self.assertRaisesRegex(ValueError, 'backend has changed'):
                verify_backend(backend)

    def test_job_rejects_using_the_source_as_the_psp_base(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / '0900.PAC'
            source.write_bytes(b'PAC sample')
            job = Job(str(source), str(source), str(source), str(source), str(source), folder)
            with self.assertRaisesRegex(ValueError, 'different files'):
                job.validate()
            self.assertEqual(source.read_bytes(), b'PAC sample')

    def test_settings_roundtrip_and_corrupt_file_recovery(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'WRESTLER_IMPORTER_DATA': folder}):
            values = settings.defaults()
            values['source'] = 'C:\\my models\\0900.pac'
            settings.save(values)
            self.assertEqual(settings.load(), values)
            (Path(folder) / 'settings.json').write_text('{bad json')
            self.assertEqual(settings.load(), settings.defaults())

    def test_worker_failure_reports_error_and_does_not_create_an_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            values = {k: str(path / 'missing') for k in ('source', 'base', 'reference', 'editor', 'blender')}
            values.update(output_parent=str(path / 'exports'), target_game='SVR 2011 PSP')
            request = path / 'request.json'
            request.write_text(json.dumps(values))
            self.assertEqual(worker(request), 1)
            result = json.loads((path / 'result.json').read_text())
            self.assertFalse(result['ok'])
            self.assertTrue((path / 'worker.log').exists())
            self.assertFalse((path / 'exports').exists())


if __name__ == '__main__':
    unittest.main()
