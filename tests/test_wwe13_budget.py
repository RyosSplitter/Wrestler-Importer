"""WWE13 costume policy and validation routing, without game assets."""
import unittest
from unittest.mock import patch

from tools.wwe13_budget import budget, result_role
from tools.wwe13_wii_trial import validate_trial


class BudgetTests(unittest.TestCase):
    def test_explicit_entrance_and_unchanged_ring_ceiling(self):
        self.assertEqual(budget()['max_pac_bytes'], 152064)
        self.assertEqual(budget('entrance')['max_pac_bytes'], 180000)
        self.assertEqual(budget('entrance')['maximum_sector_aligned_bytes'], 178176)
        self.assertGreater(180224, budget('entrance')['max_pac_bytes'])

    def test_old_variant_reports_are_not_reinterpreted(self):
        self.assertEqual(result_role(dict(variant=1)), 'ring')
        self.assertEqual(result_role(dict(budget=dict(costume_role='ring',max_pac_bytes=148000))), 'ring')
        self.assertEqual(result_role(dict(variant=2, budget=budget('entrance'))), 'entrance')
        with self.assertRaises(ValueError):
            result_role(dict(budget=dict(costume_role='ring', max_pac_bytes=180000)))
        with self.assertRaises(ValueError):
            budget('unknown')

    def test_native_validator_uses_same_role_limit(self):
        # Stop at native validation so all downstream geometry/bone checks stay
        # real in integration runs; this tests the formerly hardcoded cap.
        class NativeReached(Exception):
            pass
        for role in ('ring', 'entrance'):
            with patch('tools.wwe13_wii_trial.validate_pac', side_effect=NativeReached) as native:
                with self.assertRaises(NativeReached):
                    validate_trial(b'candidate', b'base', [], costume_role=role)
                self.assertEqual(native.call_args.args[2], budget(role)['max_pac_bytes'])


if __name__ == '__main__':
    unittest.main()
