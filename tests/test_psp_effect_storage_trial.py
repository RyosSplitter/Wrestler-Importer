import unittest
from pathlib import Path
from tools.psp_effect_storage_trial import compact_effect_storage
from tools.pac_repack import rewrite_sections, texture_table
from tools.psp_mesh_merge_trial import sections
from desktop.texture_optimizer.candidates import read_gim


class EffectStorageTrialTests(unittest.TestCase):
    def fixture(self):
        folder = Path(__file__).parent / 'fixtures/hctp_psp'
        pac = (folder / 'psp-quad.pac').read_bytes(); gim = (folder / 'skin-t4.gim').read_bytes()
        return rewrite_sections(pac, {}, additions={8: texture_table(['blood'], [gim], gim_reader=read_gim),
                                                  12: b'Preserved opaque donor metadata' * 30})

    def test_every_decoded_section_and_other_stored_payload_is_exact(self):
        source = self.fixture(); before = bytes(source); result, report = compact_effect_storage(source)
        self.assertTrue(report['changed']); self.assertGreater(report['reclaimed_stored_bytes'], 0)
        self.assertEqual(source, before)
        a, b = list(sections(source)), list(sections(result))
        self.assertEqual([s['id'] for s, _ in a], [s['id'] for s, _ in b])
        for (x, p), (y, q) in zip(a, b):
            self.assertEqual(p, q)
            if x['id'] != 8:
                self.assertEqual(source[x['offset']:x['offset'] + x['size']], result[y['offset']:y['offset'] + y['size']])

    def test_repeated_compaction_is_idempotent(self):
        first, _ = compact_effect_storage(self.fixture()); second, report = compact_effect_storage(first)
        self.assertEqual(first, second); self.assertFalse(report['changed'])

    def test_missing_effect_table_is_unchanged(self):
        p = Path(__file__).parent / 'fixtures/hctp_psp/psp-quad.pac'; raw = p.read_bytes()
        result, report = compact_effect_storage(raw)
        self.assertEqual(raw, result); self.assertFalse(report['changed'])

    def test_unrecognized_effect_payload_is_rejected(self):
        p = Path(__file__).parent / 'fixtures/hctp_psp/psp-quad.pac'; raw = rewrite_sections(p.read_bytes(), {}, additions={8: b'Not a texture table'})
        with self.assertRaises(ValueError): compact_effect_storage(raw)


if __name__ == '__main__': unittest.main()
