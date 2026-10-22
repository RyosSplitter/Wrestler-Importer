"""Windows-only portable build. Includes no user/reference/game PAC assets."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAME='PS2PSP-Pac-Converter'

def download(url,path):
    path=Path(path)
    request=urllib.request.Request(url,headers={'User-Agent':'PS2PSP-Pac-Converter-build/1.0 (+https://github.com/RyosSplitter/Wrestler-Importer)'})
    try:
        with urllib.request.urlopen(request,timeout=90) as response,path.open('wb') as out:shutil.copyfileobj(response,out)
    except urllib.error.HTTPError as exc:
        detail=exc.read(600).decode('utf-8',errors='replace')
        raise RuntimeError('Official runtime download returned HTTP %d for %s: %s'%(exc.code,url,detail)) from exc

def build(name=NAME):
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
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name',name,
          '--collect-all','tkinterdnd2','--collect-all','rtree','--collect-submodules','tools','--collect-submodules','model_qa',
          '--collect-submodules','desktop','--collect-submodules','stable_pipeline']
    for folder in ('tools','desktop','model_qa'):args+=['--add-data',str(resource/folder)+';'+folder]
    args+=[str(ROOT/'ps2psp_converter.py')];subprocess.run(args,cwd=ROOT,check=True)
    destination=ROOT/'dist'/name;runtime=destination/'runtime';runtime.mkdir()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if Path(member.filename).is_absolute() or '..' in Path(member.filename).parts:raise ValueError('Unsafe Blender archive path')
        z.extractall(runtime)
    (runtime/'blender-4.3.2-windows-x64').rename(runtime/'blender')
    sources=destination/'sources';sources.mkdir();shutil.copy2(source,sources/source.name)
    for folder in ('desktop','tools','model_qa','app','stable_pipeline'):
        shutil.copytree(ROOT/folder,sources/'converter'/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (sources/'converter/experiments').mkdir()
    shutil.copy2(ROOT/'experiments/texture_fidelity_selection.py',sources/'converter/experiments/texture_fidelity_selection.py')
    for filename in ('default_texture_quality.py','texture_budget_trial.py'):
        shutil.copy2(ROOT/'experiments'/filename,sources/'converter/experiments'/filename)
    for filename in ('ps2psp_converter.py','requirements-desktop.txt','requirements-qa.txt','requirements.txt','REIMPLEMENTATION_GUIDE.txt'):
        shutil.copy2(ROOT/filename,sources/'converter'/filename)
    shutil.copytree(ROOT/'docs/hctp-psp',sources/'converter/docs/hctp-psp')
    for path in (ROOT/'docs').glob('portable-*'):
        if path.is_file():shutil.copy2(path,sources/'converter/docs'/path.name)
    for filename in ('rock-head-qa-investigation.md','rock-scalp-layout-control.md','next-update.md',
                     'rvd-texture-budget-experiment.md','source-skinning-identity.md','texture-quality-v025-native-summary.json',
                     'jbi-app-integration.md','jbi-rock-arm-accessory-trial.md','jbi-provenance-correction.json'):
        shutil.copy2(ROOT/'docs'/filename,sources/'converter/docs'/filename)
    for filename in ('offline-retexture-editor.md','wwe13-wii-app-preview.md','wwe13-wii-packet-scale-hotfix.md','wwe13-edge-texture-refinement-04.md','wwe13-wii-geometry-opacity-03.md','pac-size-policy.md'):
        shutil.copy2(ROOT/'docs'/filename,sources/'converter/docs'/filename)
    focused_tests=sources/'converter/tests';focused_tests.mkdir()
    (focused_tests/'__init__.py').write_text('')
    for filename in ('test_default_textures.py','test_texture_budget_trial.py','test_suite_workspace.py','test_pac_browser.py','test_edit_folder.py','test_pac_validator.py','test_portable_skinning.py','test_compatibility_validator.py',
                     'test_retexture.py','test_jbi_rig.py','test_jbi_adapter.py','test_sym_source.py','test_pac_inspect.py'):
        shutil.copy2(ROOT/'tests'/filename,focused_tests/filename)
    for filename in ('test_wii_app.py','test_wii_source_encoding.py','test_wwe13_wii_model.py','test_wwe13_wii_corpus.py','test_wwe13_wii_inspect.py','test_wwe13_texture_format_trial.py','test_psp_effect_storage_trial.py','test_palette_quality_qa.py','test_alpha_coverage.py'):
        shutil.copy2(ROOT/'tests'/filename,focused_tests/filename)
    # Procedural binary conformance vectors, not game-derived assets. Store
    # them in an archive so extracted runtime asset checks remain strict.
    fixture_archive=sources/'converter/procedural-fixtures.zip'
    with zipfile.ZipFile(fixture_archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in (ROOT/'tests/fixtures/hctp_psp').glob('*'):
            if path.is_file():z.write(path,path.relative_to(ROOT).as_posix())
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
    shutil.copy2(ROOT/('docs/portable-model-suite.md' if name=='PSP-Model-Suite' else 'docs/portable-desktop.md'),destination/'README.md');shutil.copy2(ROOT/'docs/portable-distribution.md',destination/'DISTRIBUTION.md')
    for path in destination.rglob('*'):
        if path.suffix.lower() in ('.pac','.yobj','.obj','.gim','.png') and 'runtime' not in path.parts:raise ValueError('Unexpected model/texture asset in portable build: '+str(path))
    files={str(p.relative_to(destination)).replace('\\','/'):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'MANIFEST.json').write_text(json.dumps(dict(blender_official_zip_sha256=wanted,blender_source_sha256=hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),files=files),indent=2),encoding='utf-8')
    print(destination)

if __name__=='__main__':
    try:build('PSP-Model-Suite' if '--suite' in sys.argv else NAME)
    except Exception:
        import traceback
        error=traceback.format_exc().replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::error title=Portable build::'+error,flush=True)
        raise
