"""Package an executable-only 0.2.1 overlay; Windows CI tests it on release 0.2."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def build():
    folder=ROOT/'dist'/'creator-donor-patch';folder.mkdir()
    executable=ROOT/'dist/PSP-Model-Creator/PSP-Model-Creator.exe'
    shutil.copy2(executable,folder/executable.name)
    shutil.copy2(ROOT/'docs/creator-donor-patch-021.md',folder/'ADD-DONORS-README.md')
    for name in ('model_creator/library.py','model_creator/gui.py','model_creator/smoke.py','model_creator/core.py',
                 'tests/test_creator_donor_import.py','tools/build_creator_patch.py'):
        destination=folder/'sources'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
    files={p.relative_to(folder).as_posix():hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in folder.rglob('*') if p.is_file()}
    (folder/'DONOR-PATCH-MANIFEST.json').write_text(json.dumps(dict(version='0.2.1',requires='PSP Model Creator 0.2 Windows x64',
        base_release='creator-preview-5-bf7111bd55032b469cb6dc861410de03b7bbb02b',runtime_or_catalog_replaced=False,files=files),indent=2)+'\n',encoding='utf-8')
    path=Path(shutil.make_archive(str(ROOT/'dist/PSP-Model-Creator-0.2.1-Donor-Patch'),'zip',folder))
    Path(str(path)+'.sha256').write_text(hashlib.file_digest(path.open('rb'),'sha256').hexdigest()+'  '+path.name+'\n')
    print(path,path.stat().st_size)


if __name__=='__main__':build()
