"""Directory browsing does not decode PACs or modify source files."""
from pathlib import Path
import tempfile
import unittest

from desktop.pac_browser import pac_files, matching_files


class PacFolderTests(unittest.TestCase):
    def test_only_direct_pac_files_are_listed_case_insensitively_in_natural_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('Model10.pac','Model2.PAC','Model1.PaC','readme.txt'):
                (root/name).write_bytes(name.encode())
            (root/'folder.pac').mkdir()
            (root/'folder.pac'/'Nested.pac').write_bytes(b'nested, not a direct child')
            listed = pac_files(root)
            self.assertEqual([p.name for p in listed], ['Model1.PaC','Model2.PAC','Model10.pac'])
            for path in listed:
                self.assertEqual(path.read_bytes(), path.name.encode())

    def test_filename_filter_is_literal_case_insensitive_and_preserves_order(self):
        files = [Path('A.PAC'),Path('Benoit (Ring).pac'),Path('Benoit (Hat).PAC'),Path('[Special].pac')]
        self.assertEqual(matching_files(files,' BENOIT '),files[1:3])
        self.assertEqual(matching_files(files,'['),files[3:])
        self.assertEqual(matching_files(files,''),files)
        self.assertEqual(matching_files(files,'missing'),[])

    def test_empty_and_unavailable_folder_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(pac_files(root),[])
            with self.assertRaises(FileNotFoundError):pac_files(root/'missing')
            path = root/'not a folder.pac';path.write_bytes(b'untouched')
            with self.assertRaises(NotADirectoryError):pac_files(path)


if __name__=='__main__':unittest.main()
