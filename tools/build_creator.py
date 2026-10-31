"""Separate Windows creator build, with the explicitly supplied native library."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
NAME='PSP-Model-Creator'


def build():
    if sys.platform!='win32':raise SystemExit('Use the Windows creator GitHub workflow.')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
                    '--name',NAME,'--collect-all','rtree','--collect-submodules','model_creator','--exclude-module','bpy',
                    '--add-data',str(ROOT/'model_creator')+';model_creator',str(ROOT/'psp_model_creator.py')],cwd=ROOT,check=True)
    destination=ROOT/'dist'/NAME;sources=destination/'sources';sources.mkdir()
    # Include source + tests/docs for reproducibility. Never package downloads,
    # local study files, Blender, third-party tool binaries or private PACs.
    for directory in ('model_creator','desktop','model_qa','tools','stable_pipeline','app','tests'):
        for path in (ROOT/directory).rglob('*'):
            if path.is_file() and path.suffix in ('.py','.json','.md','.txt') and '__pycache__' not in path.parts:
                out=sources/path.relative_to(ROOT);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out)
    for name in ('psp_model_creator.py','requirements.txt','requirements-qa.txt','requirements-desktop.txt'):
        shutil.copy2(ROOT/name,sources/name)
    shutil.copy2(ROOT/'docs/creator-050.md',destination/'README.md')
    shutil.copy2(ROOT/'docs/standalone-model-creator.md',sources/'CREATOR.md')
    shutil.copy2(ROOT/'docs/creator-library-02.md',destination/'LIBRARY.md')
    shutil.copy2(ROOT/'docs/creator-030.md',destination/'ADD-DONORS.md')
    shutil.copy2(ROOT/'docs/creator-031.md',sources/'CREATOR-WAISTLINE.md')
    shutil.copy2(ROOT/'docs/creator-040.md',sources/'CREATOR-MORPH.md')
    shutil.copy2(ROOT/'docs/creator-050.md',sources/'CREATOR-UV.md')
    library=ROOT/'creator_library'
    from model_creator.library import Library
    prepared=Library(library)
    for index in range(len(prepared.entries)):prepared.source(index)
    shutil.copytree(library,destination/'creator_library')
    licenses=destination/'licenses';licenses.mkdir();distributions=[]
    for dist in metadata.distributions():
        rows=[]
        for item in dist.files or []:
            if any(word in item.name.casefold() for word in ('license','copying','notice')):
                path=Path(dist.locate_file(item))
                if path.is_file():
                    out=licenses/(dist.metadata['Name']+'-'+dist.version)/str(item).replace(':','_');out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out);rows.append(out.relative_to(destination).as_posix())
        distributions.append(dict(name=dist.metadata['Name'],version=dist.version,license=dist.metadata.get('License-Expression',dist.metadata.get('License')),files=rows))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copy2(python_license,licenses/'Python-LICENSE.txt')
    for path in (Path(sys.base_prefix)/'tcl').rglob('*'):
        if path.is_file() and path.name.casefold().startswith(('license','copying')):
            target=licenses/'Tcl-Tk'/path.relative_to(Path(sys.base_prefix)/'tcl');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    (licenses/'python-distributions.json').write_text(json.dumps(distributions,indent=2),encoding='utf-8')
    forbidden={'.pac','.yobj','.obj','.gim','.bms','.7z'}
    approved_assets={destination/'creator_library'/entry['file'] for entry in prepared.entries}
    for p in destination.rglob('*'):
        if p.suffix.casefold() in forbidden and p not in approved_assets:raise ValueError('Unexpected asset in application bundle: '+str(p))
    files={p.relative_to(destination).as_posix():hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'MANIFEST.json').write_text(json.dumps(dict(version='0.5.0',blender_bundled=False,blender_runtime='Select existing Blender 4.3.2 from PSP Model Suite for morph export',game_assets_bundled=True,
        prepared_models=len(prepared.entries),assets='User-supplied native library; original rights retained.',files=files),indent=2),encoding='utf-8')
    print('Creator ready:',destination)


if __name__=='__main__':build()
