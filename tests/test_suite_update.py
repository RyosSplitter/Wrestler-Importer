import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from tools.build_suite_update import build,digest


class SuiteUpdateTests(unittest.TestCase):
    def fixture(self,folder):
        folder=Path(folder);new=folder/'PSP-Model-Suite';new.mkdir()
        (new/'runtime').mkdir();(new/'runtime/same.dll').write_bytes(b'identical runtime')
        (new/'PSP-Model-Suite.exe').write_bytes(b'new executable')
        hashes={p.relative_to(new).as_posix():digest(p) for p in new.rglob('*') if p.is_file()}
        (new/'MANIFEST.json').write_text(json.dumps(dict(files=hashes)))
        previous=folder/'old.zip'
        old=dict(hashes);old['PSP-Model-Suite.exe']=hashlib.sha256(b'old executable').hexdigest()
        with zipfile.ZipFile(previous,'w') as z:
            z.writestr('PSP-Model-Suite/MANIFEST.json',json.dumps(dict(files=old)))
            z.writestr('PSP-Model-Suite/PSP-Model-Suite.exe',b'old executable')
            z.writestr('PSP-Model-Suite/runtime/same.dll',b'identical runtime')
        return previous,new,folder/'update.zip'

    def test_changed_files_only_and_manifest_reconstruct_the_new_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new,out=self.fixture(tmp);r=build(old,new,out,digest(old))
            self.assertEqual(r['changed_files'],['PSP-Model-Suite.exe']);self.assertEqual(r['unchanged_file_count'],1)
            with zipfile.ZipFile(out) as z:
                self.assertNotIn('PSP-Model-Suite/runtime/same.dll',z.namelist())
                self.assertEqual(z.read('PSP-Model-Suite/PSP-Model-Suite.exe'),b'new executable')
                self.assertEqual(z.read('PSP-Model-Suite/MANIFEST.json'),(new/'MANIFEST.json').read_bytes())
            self.assertEqual(Path(str(out)+'.sha256').read_text().split()[0],digest(out))
            with self.assertRaises(FileExistsError):build(old,new,out,digest(old))

    def test_changed_runtime_is_included_rather_than_assumed_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new,out=self.fixture(tmp);(new/'runtime/same.dll').write_bytes(b'changed native library')
            r=json.loads((new/'MANIFEST.json').read_text());r['files']['runtime/same.dll']=digest(new/'runtime/same.dll');(new/'MANIFEST.json').write_text(json.dumps(r))
            result=build(old,new,out,digest(old));self.assertIn('runtime/same.dll',result['changed_files'])

    def test_wrong_old_zip_or_modified_new_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new,out=self.fixture(tmp)
            with self.assertRaisesRegex(ValueError,'checksum'):build(old,new,out,'0'*64)
            (new/'PSP-Model-Suite.exe').write_bytes(b'unverified')
            with self.assertRaisesRegex(ValueError,'manifest mismatch'):build(old,new,out,digest(old))

    def test_file_removals_are_not_silently_left_in_an_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new,out=self.fixture(tmp);r=json.loads((new/'MANIFEST.json').read_text());del r['files']['runtime/same.dll'];(new/'MANIFEST.json').write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'cannot remove'):build(old,new,out,digest(old))


if __name__=='__main__':unittest.main()
