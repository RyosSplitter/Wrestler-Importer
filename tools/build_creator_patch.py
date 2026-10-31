"""Package an executable-only 0.3.1 overlay; Windows CI tests it on release 0.2."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def build():
    folder=ROOT/'dist'/'creator-donor-patch';folder.mkdir()
    executable=ROOT/'dist/PSP-Model-Creator/PSP-Model-Creator.exe'
    shutil.copy2(executable,folder/executable.name)
    shutil.copy2(ROOT/'docs/creator-040.md',folder/'MORPH-README.md')
    # Blender reads these Python sources directly; the old runtime has no morph worker data.
    shutil.copytree(ROOT/'dist/PSP-Model-Creator/_internal/model_creator',folder/'_internal/model_creator',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('model_creator/library.py','model_creator/gui.py','model_creator/smoke.py','model_creator/core.py','model_creator/parts.py','model_creator/waist.py','model_creator/rigging.py','model_creator/textures.py',
                 'tests/test_creator_donor_import.py','tests/test_creator_030.py','tests/test_creator_waist.py','tools/build_creator_patch.py'):
        destination=folder/'sources'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
    for directory in ('model_creator/morph',):
        shutil.copytree(ROOT/directory,folder/'sources'/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('desktop/blender_runtime.py','tests/test_morph_studio.py','docs/creator-040.md'):
        destination=folder/'sources'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
    files={p.relative_to(folder).as_posix():hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in folder.rglob('*') if p.is_file()}
    (folder/'DONOR-PATCH-MANIFEST.json').write_text(json.dumps(dict(version='0.4.0',requires='PSP Model Creator 0.2 through 0.3.1 Windows x64; existing Suite Blender 4.3.2 for morph export',
        base_release='creator-preview-5-bf7111bd55032b469cb6dc861410de03b7bbb02b',runtime_or_catalog_replaced=False,worker_sources_added=True,files=files),indent=2)+'\n',encoding='utf-8')
    path=Path(shutil.make_archive(str(ROOT/'dist/PSP-Model-Creator-0.4.0-Creator-Patch'),'zip',folder))
    Path(str(path)+'.sha256').write_text(hashlib.file_digest(path.open('rb'),'sha256').hexdigest()+'  '+path.name+'\n')
    print(path,path.stat().st_size)


if __name__=='__main__':build()
