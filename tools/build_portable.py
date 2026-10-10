"""Windows-only portable build. Includes no user/reference/game PAC assets."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAME='PS2PSP-Pac-Converter'

def download(url,path):
    path=Path(path)
    with urllib.request.urlopen(url,timeout=90) as response,path.open('wb') as out:shutil.copyfileobj(response,out)

def build():
    if sys.platform!='win32':raise SystemExit('Build on Windows x64, or use the Windows portable GitHub workflow.')
    cache=ROOT/'build/portable-cache';cache.mkdir(parents=True,exist_ok=True)
    archive=cache/'blender-4.3.2-windows-x64.zip';checks=cache/'blender-4.3.2.sha256'
    release='https://download.blender.org/release/Blender4.3/'
    download(release+checks.name,checks)
    wanted=next(line.split()[0] for line in checks.read_text().splitlines() if line.split()[-1].lstrip('*')==archive.name)
    if not archive.exists():download(release+archive.name,archive)
    if hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=wanted:raise ValueError('Official Blender ZIP checksum mismatch; build stopped.')
    source=cache/'blender-4.3.2.tar.xz'
    if not source.exists():download('https://download.blender.org/source/'+source.name,source)
    resource=ROOT/'build/portable-resources'
    if resource.exists():shutil.rmtree(resource)
    for folder in ('tools','desktop','model_qa'):
        for path in (ROOT/folder).rglob('*'):
            if path.suffix in ('.py','.json') and '__pycache__' not in path.parts:
                dest=resource/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name',NAME,
          '--collect-all','tkinterdnd2','--collect-all','rtree','--collect-submodules','tools','--collect-submodules','model_qa',
          '--collect-submodules','desktop','--collect-submodules','stable_pipeline']
    for folder in ('tools','desktop','model_qa'):args+=['--add-data',str(resource/folder)+';'+folder]
    args+=[str(ROOT/'ps2psp_converter.py')];subprocess.run(args,cwd=ROOT,check=True)
    destination=ROOT/'dist'/NAME;runtime=destination/'runtime';runtime.mkdir()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if Path(member.filename).is_absolute() or '..' in Path(member.filename).parts:raise ValueError('Unsafe Blender archive path')
        z.extractall(runtime)
    (runtime/'blender-4.3.2-windows-x64').rename(runtime/'blender')
    sources=destination/'sources';sources.mkdir();shutil.copy2(source,sources/source.name)
    for folder in ('desktop','tools','model_qa','app','stable_pipeline'):
        shutil.copytree(ROOT/folder,sources/'converter'/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for filename in ('ps2psp_converter.py','requirements-desktop.txt','requirements-qa.txt','requirements.txt','REIMPLEMENTATION_GUIDE.txt'):
        shutil.copy2(ROOT/filename,sources/'converter'/filename)
    shutil.copytree(ROOT/'docs/hctp-psp',sources/'converter/docs/hctp-psp')
    notices=destination/'licenses';notices.mkdir();manifest=[]
    for dist in metadata.distributions():
        license_files=[]
        for item in dist.files or []:
            if any(word in item.name.lower() for word in ('license','copying','notice')):
                path=Path(dist.locate_file(item))
                if path.is_file():
                    out=notices/(dist.metadata['Name']+'-'+dist.version)/str(item).replace(':','_');out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out);license_files.append(str(out.relative_to(destination)))
        manifest.append(dict(name=dist.metadata['Name'],version=dist.version,license=dist.metadata.get('License-Expression',dist.metadata.get('License')),license_files=license_files))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copy2(python_license,notices/'Python-LICENSE.txt')
    for path in (Path(sys.base_prefix)/'tcl').rglob('*'):
        if path.is_file() and path.name.lower().startswith(('license','copying')):
            dest=notices/'Tcl-Tk'/path.relative_to(Path(sys.base_prefix)/'tcl');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    (notices/'python-distributions.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'docs/portable-desktop.md',destination/'README.md');shutil.copy2(ROOT/'docs/portable-distribution.md',destination/'DISTRIBUTION.md')
    for path in destination.rglob('*'):
        if path.suffix.lower() in ('.pac','.yobj','.obj','.gim','.png') and 'runtime' not in path.parts:raise ValueError('Unexpected model/texture asset in portable build: '+str(path))
    files={str(p.relative_to(destination)).replace('\\','/'):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'MANIFEST.json').write_text(json.dumps(dict(blender_official_zip_sha256=wanted,blender_source_sha256=hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),files=files),indent=2),encoding='utf-8')
    print(destination)

if __name__=='__main__':build()
