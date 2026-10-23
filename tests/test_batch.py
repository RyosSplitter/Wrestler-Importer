"""Batch continuation, costume selection, cancellation and protected exports."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.batch import counts, load_result, plan_files, run_batch, save_reviewed, write_state


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.base = self.file('base.pac')

    def file(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'PAC ')
        return path

    def request(self, files, **options):
        root = self.root / 'batch'
        root.mkdir()
        path = root / 'request.json'
        write_state(path, dict(files=list(map(str, files)), options=dict(
            base=str(self.base), source_format='hctp', texture_mode='Default', **options)))
        return path

    def fake_spawn(self, script):
        """Simulate child exits; actual native conversions are covered by smoke."""
        calls = []
        class Child:
            def __init__(self, job, request):
                self.job, self.request = job, request
                self.returncode = None
                self.polls = 0
            def poll(self):
                self.polls += 1
                if self.polls == 1:
                    (self.job / 'events.jsonl').write_text('{"percent":40,"message":"Reducing"}\n{"percent":', encoding='utf-8')
                    return None
                self.returncode = script(self.job, self.request)
                return self.returncode
            def wait(self):
                if self.returncode is None:
                    self.returncode = script(self.job, self.request)
                return self.returncode
        def spawn(args, **kwargs):
            path = Path(args[-1])
            request = json.loads(path.read_text())
            calls.append(request)
            return Child(path.parent, request)
        return spawn, calls

    def success(self, job, request):
        preview = job / 'preview'
        preview.mkdir()
        candidate = job / 'candidate.pac'
        candidate.write_bytes(b'candidate')
        write_state(job / 'success.json', dict(pac=str(candidate), preview=str(preview),
                    source=request['source'], source_entry=request.get('source_entry', ''), base=request['base']))
        return 0

    def test_bad_file_is_reported_and_duplicate_paths_are_not_queued_twice(self):
        good = self.file('one.pac')
        rows = plan_files([good, good, self.root / 'missing.pac'], 'hctp')
        self.assertEqual([row['state'] for row in rows], ['pending', 'skipped'])
        self.assertIn('existing', rows[1]['error'])

    def test_archive_costumes_are_separate_and_use_the_chosen_source_game(self):
        source = self.file('archive.pac')
        for game, costumes in [('jbi', ['0000', '0100']), ('wwe13-wii', ['00', '01'])]:
            with self.subTest(game=game), patch('desktop.batch.adapter') as factory:
                factory.return_value.catalogue.return_value = dict(entries=[dict(id=value) for value in costumes])
                rows = plan_files([source], game)
                factory.assert_called_once_with(game)
                self.assertEqual([row['source_entry'] for row in rows], costumes)
                self.assertTrue(all(row['source'] == str(source) for row in rows))

    def test_archive_catalogue_error_does_not_drop_the_next_file(self):
        a, b = self.file('a.pac'), self.file('b.pac')
        with patch('desktop.batch.adapter') as factory:
            factory.return_value.catalogue.side_effect = [ValueError('bad directory'), dict(entries=[])]
            rows = plan_files([a, b], 'jbi')
        self.assertEqual([row['state'] for row in rows], ['skipped', 'pending'])
        self.assertEqual(rows[0]['error'], 'bad directory')

    def test_input_limit_is_checked_before_catalogue_reads(self):
        large = self.file('large.pac')
        with large.open('r+b') as stream:
            stream.truncate(32 * 1024 * 1024 + 1)
        with patch('desktop.batch.adapter') as factory:
            rows = plan_files([large], 'jbi')
            factory.return_value.catalogue.assert_not_called()
        self.assertEqual(rows[0]['state'], 'skipped')
        self.assertIn('32 MiB', rows[0]['error'])

    def test_success_failure_crash_and_later_success_continue_in_separate_jobs(self):
        files = [self.file(name) for name in ('a.pac', 'bad.pac', 'crash.pac', 'z.pac')]
        before = [path.read_bytes() for path in files]
        request = self.request(files)
        jobs = []
        def script(job, options):
            jobs.append(job)
            name = Path(options['source']).name
            if name == 'bad.pac':
                write_state(job / 'failure.json', dict(error='Native analytical pose gate failed', cancelled=False))
                return 1
            if name == 'crash.pac':
                return 7
            return self.success(job, options)
        spawn, calls = self.fake_spawn(script)
        self.assertEqual(run_batch(request, ['converter'], spawn=spawn, pause=lambda _: None), 0)
        state = json.loads(request.with_name('summary.json').read_text())
        self.assertEqual([row['state'] for row in state['items']], ['succeeded', 'skipped', 'skipped', 'succeeded'])
        self.assertEqual(len(set(jobs)), 4)
        self.assertEqual(state['items'][1]['error'], 'Native analytical pose gate failed')
        self.assertIn('code 7', state['items'][2]['error'])
        self.assertEqual(load_result(state['items'][3])['source'], str(files[3]))
        self.assertIsNone(load_result(state['items'][1]))
        self.assertEqual([path.read_bytes() for path in files], before)
        text = request.with_name('summary.txt').read_text()
        self.assertIn('2 succeeded | 2 skipped', text)

    def test_worker_start_failure_is_skipped(self):
        request = self.request([self.file('a.pac'), self.file('b.pac')])
        successful_spawn, calls = self.fake_spawn(self.success)
        count = 0
        def spawn(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 1:
                raise OSError('process creation failed')
            return successful_spawn(*args, **kwargs)
        run_batch(request, ['converter'], spawn=spawn, pause=lambda _: None)
        state = json.loads(request.with_name('summary.json').read_text())
        self.assertEqual([row['state'] for row in state['items']], ['skipped', 'succeeded'])

    def test_cancel_retains_completed_candidate_cancels_current_and_leaves_rest_unrun(self):
        request = self.request([self.file(name) for name in ('done.pac', 'cancel.pac', 'next.pac')])
        def script(job, options):
            if Path(options['source']).name == 'done.pac':
                return self.success(job, options)
            self.assertTrue((job / 'cancel').is_file())
            write_state(job / 'failure.json', dict(error='Conversion cancelled.', cancelled=True))
            return 2
        spawn, calls = self.fake_spawn(script)
        def pause(_):
            if len(calls) == 2:
                request.with_name('cancel').touch()
        # Pause first requests cancellation; the next poll forwards the marker
        # before the fake worker exits.
        original_spawn = spawn
        def wrapped_spawn(*args, **kwargs):
            child = original_spawn(*args, **kwargs)
            if len(calls) == 2:
                request.with_name('cancel').touch()
            return child
        run_batch(request, ['converter'], spawn=wrapped_spawn, pause=pause)
        state = json.loads(request.with_name('summary.json').read_text())
        self.assertEqual(state['phase'], 'cancelled')
        self.assertEqual([row['state'] for row in state['items']], ['succeeded', 'cancelled', 'not-run'])
        self.assertIsNotNone(load_result(state['items'][0]))
        self.assertEqual(len(calls), 2)

    def test_mismatched_costume_result_is_never_available_for_review(self):
        request = self.request([self.file('a.pac')])
        def script(job, options):
            self.success(job, dict(options, source_entry='wrong'))
            return 0
        spawn, _ = self.fake_spawn(script)
        run_batch(request, ['converter'], spawn=spawn, pause=lambda _: None)
        state = json.loads(request.with_name('summary.json').read_text())
        self.assertEqual(state['items'][0]['state'], 'skipped')
        self.assertIn('different costume', state['items'][0]['error'])

    def test_only_reviewed_success_can_save_and_all_batch_inputs_are_protected(self):
        first, second = self.file('a.pac'), self.file('b.pac')
        request = self.request([first, second])
        spawn, _ = self.fake_spawn(self.success)
        run_batch(request, ['converter'], spawn=spawn, pause=lambda _: None)
        state = json.loads(request.with_name('summary.json').read_text())
        row = state['items'][0]
        with patch('desktop.storage.save_as', return_value='saved') as save:
            for protected in (first, second, self.base, request.parent / 'overwrite.pac'):
                with self.subTest(protected=protected), self.assertRaises(ValueError):
                    save_reviewed(state, row, protected, request.parent)
            hardlink = self.root / 'link.pac'
            os.link(second, hardlink)
            with self.assertRaises(ValueError):
                save_reviewed(state, row, hardlink, request.parent)
            save.assert_not_called()
            self.assertEqual(save_reviewed(state, row, self.root / 'saved.pac', request.parent), 'saved')
            save.assert_called_once()
        with self.assertRaises(ValueError):
            save_reviewed(state, dict(row, state='skipped'), self.root / 'bad.pac', request.parent)


if __name__ == '__main__':
    unittest.main()
