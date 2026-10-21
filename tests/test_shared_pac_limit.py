"""One exact in-ring policy across allocation, export and readback."""
import inspect
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from desktop.limits import IN_RING_MAX_PAC_BYTES, aligned_ceiling
from desktop.core import validate_pac
from desktop.default_textures import upgrade
from desktop.texture_optimizer.pac import optimize_pac
from desktop.texture_modes import downgrade_pac
from desktop.maximum_downgrade import fit_pac
from desktop.skinning import apply_single_slot_compatibility
from desktop.pac_validator import validate_pac as suite_validate
from desktop.source_reference_qa import validate_pac as reference_validate
from model_creator.core import MAX_BYTES
from model_creator.library import Library
from model_creator.textures import fit_textures
from model_qa.pipeline import run as compare
from tools.wwe13_texture_trial import allocate
from tools.sym_trial import run as sym_run
from tools.generate_conformance_fixtures import vectors
from desktop.texture_optimizer.candidates import read_gim


class SharedLimitTests(unittest.TestCase):
    def test_exact_units_and_aligned_ceiling(self):
        self.assertEqual(IN_RING_MAX_PAC_BYTES,152064)
        self.assertEqual(IN_RING_MAX_PAC_BYTES/1024,148.5)
        self.assertEqual(aligned_ceiling(),151552)

    def test_all_active_entry_point_defaults_share_the_limit(self):
        for function,parameter in [(validate_pac,'max_bytes'),(upgrade,'target'),
                (optimize_pac,'target'),(downgrade_pac,'target'),(fit_pac,'target'),
                (apply_single_slot_compatibility,'max_bytes'),(suite_validate,'max_bytes'),
                (reference_validate,'max_bytes'),(fit_textures,'target'),(compare,'max_pac_bytes'),
                (allocate,'target'),(sym_run,'max_bytes')]:
            with self.subTest(function=function.__module__+'.'+function.__name__):
                self.assertEqual(inspect.signature(function).parameters[parameter].default,IN_RING_MAX_PAC_BYTES)
        profile=Path(__file__).resolve().parents[1]/'desktop/profiles/hctp-v1.json'
        self.assertEqual(json.loads(profile.read_text())['max_pac_bytes'],IN_RING_MAX_PAC_BYTES)
        self.assertEqual(MAX_BYTES,IN_RING_MAX_PAC_BYTES)

    def test_actual_native_readback_accepts_newly_available_sector(self):
        raw=vectors()['psp-quad.pac']
        # Legal opaque outer padding exercises the real native validator, not a
        # mock of the size comparison or a destructive model simplification.
        candidate=raw+bytes(151552-len(raw))
        self.assertLess(148000,len(candidate))
        validate_pac(candidate,gim_reader=read_gim)
        with self.assertRaisesRegex(ValueError,'size/alignment'):
            validate_pac(candidate,max_bytes=148000,gim_reader=read_gim)
        oversized=raw+bytes(153600-len(raw))
        with self.assertRaisesRegex(ValueError,'size/alignment'):
            validate_pac(oversized,gim_reader=read_gim)

    def test_older_donor_catalog_status_uses_current_limit_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=b'Immutable native donor snapshot'
            (root/'donor.pac').write_bytes(data)
            catalog=dict(schema='psp-model-creator.library/1',models=[dict(
                label='Donor',file='donor.pac',sha256=hashlib.sha256(data).hexdigest(),
                pac_bytes=151552,preview_only_over_budget=True)])
            path=root/'catalog.json';path.write_text(json.dumps(catalog));before=path.read_bytes()
            library=Library(root)
            self.assertFalse(library.entries[0]['preview_only_over_budget'])
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual((root/'donor.pac').read_bytes(),data)


if __name__=='__main__':unittest.main()
