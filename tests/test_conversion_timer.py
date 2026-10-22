import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.conversion_timer import ConversionTimer,duration,profile,read_history,save_trace,valid_trace


class Clock:
    def __init__(self):self.now=1000.
    def __call__(self):return self.now
    def advance(self,seconds):self.now+=seconds


class ConversionTimerTests(unittest.TestCase):
    def timer(self,history=()):
        clock=Clock();timer=ConversionTimer(history,clock=clock);timer.start();return timer,clock

    def trace(self):return dict(total_seconds=100,points=[[0,0],[20,10],[50,70],[100,100]])

    def test_monotonic_elapsed_and_first_run_estimate(self):
        t,c=self.timer();self.assertIn('calculating',t.text())
        c.advance(10);t.observe(20)
        self.assertIn('Elapsed: 00:10',t.text());self.assertIn('~00:40',t.text())
        c.advance(3);self.assertIn('~00:37',t.text())

    def test_history_uses_stage_timing_instead_of_percent_linear_time(self):
        t,c=self.timer([self.trace()]);self.assertIn('~01:40',t.text())
        c.advance(70);t.observe(50,70)
        self.assertIn('~00:30',t.text())  # 50% occurred at 70 seconds, not 50.
        c.advance(5);self.assertIn('~00:25',t.text())

    def test_repeated_progress_does_not_restart_countdown(self):
        t,c=self.timer();c.advance(10);t.observe(20);deadline=t.deadline
        c.advance(5);t.observe(20);t.observe(10)
        self.assertEqual(t.deadline,deadline);self.assertEqual(len(t.points),2)

    def test_first_long_stage_starts_a_provisional_countdown_between_events(self):
        t,c=self.timer();t.observe(10,0);c.advance(5)
        self.assertIn('~00:45',t.text());c.advance(1);self.assertIn('~00:44',t.text())

    def test_stage_overrun_never_claims_zero_or_completion(self):
        t,c=self.timer();c.advance(10);t.observe(20);c.advance(45)
        self.assertIn('updating',t.text());self.assertEqual(t.status,'running')
        t.observe(50);self.assertIn('~00:55',t.text())

    def test_worker_100_percent_still_waits_for_process_exit(self):
        t,c=self.timer();c.advance(10);t.observe(100)
        self.assertIn('Finishing',t.text());self.assertEqual(t.status,'running')
        c.advance(2);trace=t.finish('completed');self.assertEqual(trace['total_seconds'],12)
        self.assertEqual(trace['points'][-1],[100,12]);self.assertIn('Completed in 00:12',t.text())
        c.advance(100);self.assertEqual(t.elapsed,12)

    def test_cancel_and_failure_do_not_train_history(self):
        t,c=self.timer();c.advance(2);t.cancel();self.assertIn('Cancelling',t.text())
        self.assertIsNone(t.finish('cancelled'));self.assertIn('Cancelled in 00:02',t.text())
        t,c=self.timer();c.advance(3);self.assertIsNone(t.finish('failed'));self.assertIn('Failed in 00:03',t.text())

    def test_profile_separates_platform_texture_mode_role_and_geometry(self):
        a=profile({});self.assertNotEqual(a,profile(dict(source_format='jbi')))
        self.assertNotEqual(a,profile(dict(texture_mode='ATO')))
        self.assertNotEqual(a,profile(dict(costume_role='entrance')))
        self.assertNotEqual(a,profile(dict(wii_geometry='Preserve Arms')))

    def test_history_is_atomic_bounded_and_ignores_corrupt_records(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp)/'conversion-timings.json';path.write_text('corrupt')
            self.assertEqual(read_history(path),{})
            for _ in range(15):self.assertTrue(save_trace(path,'profile',self.trace()))
            self.assertEqual(len(read_history(path)['profile']),12)
            self.assertFalse(save_trace(path,'profile',dict(total_seconds=float('nan'),points=[])))
            self.assertFalse(list(Path(temp).glob('timings-*.tmp')))
            path.write_text(json.dumps(dict(schema='conversion-timings/1',profiles=[])))
            self.assertEqual(read_history(path),{})
            path.write_text(json.dumps(dict(schema='conversion-timings/1')))
            self.assertEqual(read_history(path),{})

    def test_invalid_or_out_of_order_telemetry_is_ignored(self):
        t,c=self.timer();c.advance(10);t.observe(20,8)
        for p in (float('nan'),float('inf'),-5,101,True,'50'):t.observe(p)
        self.assertEqual(t.percent,20);self.assertEqual(t.points[-1],[20,8])
        t.observe(30,-999);self.assertEqual(t.points[-1],[30,10])
        self.assertTrue(valid_trace(self.trace()))
        bad=self.trace();bad['points'][1]=[20,200];self.assertFalse(valid_trace(bad))

    def test_hour_format_and_timer_reset(self):
        self.assertEqual(duration(3661),'1:01:01');self.assertEqual(duration(4.2),'00:05')
        t,c=self.timer();c.advance(50);t.finish('failed');t.start()
        self.assertEqual(t.elapsed,0);self.assertEqual(t.points,[[0,0]])

    def test_worker_emits_elapsed_seconds_without_changing_progress_contract(self):
        import ps2psp_converter
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);request=root/'request.json'
            request.write_text(json.dumps(dict(source='source.pac',base='base.pac')))
            def job(request,work,progress,cancel):
                progress(5,'Read source');progress(100,'Ready');return {'test':'result'}
            with patch('desktop.core.run_job',side_effect=job):self.assertEqual(ps2psp_converter.worker(request),0)
            rows=[json.loads(s)for s in (root/'events.jsonl').read_text().splitlines()]
            self.assertEqual([r['percent']for r in rows],[5,100])
            self.assertTrue(all(r['elapsed_seconds']>=0 for r in rows))
            self.assertLessEqual(rows[0]['elapsed_seconds'],rows[1]['elapsed_seconds'])


if __name__=='__main__':unittest.main()
