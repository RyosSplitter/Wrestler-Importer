"""Build a complete isolated Python 3.13 / bpy 5.2.2 Windows prototype."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import zipfile

from tools.build_portable import ROOT, download

NAME = 'PS2PSP-bpy-Experiment'


def build():
    if sys.platform != 'win32': raise RuntimeError('Build on Windows x64')
    if metadata.version('bpy') != '5.2.2' or sys.version_info[:2] != (3, 13):
        raise RuntimeError('This prototype pins CPython 3.13 and bpy 5.2.2')
    cache = ROOT/'build/bpy-cache'; cache.mkdir(parents=True, exist_ok=True)
    source = cache/'blender-5.2.2.tar.xz'
    if not source.exists(): download('https://download.blender.org/source/'+source.name, source)
    # Official upstream terms, supplementing wheel's embedded native notices.
    for filename in ('COPYING', 'AUTHORS'):
        download('https://raw.githubusercontent.com/blender/blender/v5.2.2/'+filename, cache/filename)
    site = Path(sysconfig.get_path('platlib'))/'bpy'
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console', '--name', NAME,
            '--hidden-import', 'bpy', '--collect-submodules', 'tomllib', '--collect-all', 'tkinterdnd2', '--collect-all', 'rtree',
            '--collect-submodules', 'tools', '--collect-submodules', 'model_qa',
            '--collect-submodules', 'desktop', '--collect-submodules', 'stable_pipeline',
            '--collect-submodules', 'experiments.bpy', '--collect-all', 'cattrs',
            '--collect-all', 'requests', '--collect-all', 'zstandard', '--collect-all', 'Cython']
    for folder in ('tools', 'desktop', 'model_qa', 'experiments'):
        args += ['--add-data', str(ROOT/folder)+';'+folder]
    # bpy's extension rewrites its module path. Collect physical wheel contents,
    # not the rewritten scripts/modules/bpy path exposed after import.
    for p in site.iterdir():
        if p.suffix.lower() in ('.dll', '.pyd'):
            args += ['--add-binary', str(p)+';bpy']
        elif p.is_dir() and p.name != '__pycache__':
            args += ['--add-data', str(p)+';bpy/'+p.name]
    # The entry is outside experiments/bpy: PyInstaller derives its import root
    # from the entry's package, which otherwise shadows the upstream bpy wheel.
    args += [str(ROOT/'bpy_experiment.py')]
    subprocess.run(args, cwd=ROOT, check=True)
    destination = ROOT/'dist'/NAME
    for p in destination.rglob('__pycache__'): shutil.rmtree(p)
    sources = destination/'sources'; sources.mkdir()
    shutil.copy2(source, sources/source.name)
    for folder in ('desktop', 'tools', 'model_qa', 'app', 'stable_pipeline', 'experiments'):
        shutil.copytree(ROOT/folder, sources/'converter'/folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for filename in ('ps2psp_converter.py', 'bpy_experiment.py', 'requirements-desktop.txt', 'requirements-qa.txt', 'requirements.txt', 'REIMPLEMENTATION_GUIDE.txt'):
        shutil.copy2(ROOT/filename, sources/'converter'/filename)
    shutil.copytree(ROOT/'docs', sources/'converter/docs')
    licenses = destination/'licenses'; licenses.mkdir()
    for filename in ('COPYING', 'AUTHORS'): shutil.copy2(cache/filename, licenses/('Blender-'+filename))
    distributions = []
    for dist in metadata.distributions():
        names = []
        for item in dist.files or []:
            if any(s in item.name.lower() for s in ('license', 'copying', 'notice')):
                p = Path(dist.locate_file(item))
                if p.is_file():
                    out = licenses/(dist.metadata['Name']+'-'+dist.version)/str(item).replace(':', '_')
                    out.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, out)
                    names.append(str(out.relative_to(destination)))
        distributions.append(dict(name=dist.metadata['Name'], version=dist.version,
            license=dist.metadata.get('License-Expression', dist.metadata.get('License')), notices=names))
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists(): shutil.copy2(python_license, licenses/'Python-LICENSE.txt')
    for p in (Path(sys.base_prefix)/'tcl').rglob('*'):
        if p.is_file() and p.name.lower().startswith(('license', 'copying')):
            out = licenses/'Tcl-Tk'/p.relative_to(Path(sys.base_prefix)/'tcl'); out.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, out)
    (licenses/'python-distributions.json').write_text(json.dumps(distributions, indent=2), encoding='utf-8')
    (destination/'RunSelfCheck.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\nPS2PSP-bpy-Experiment.exe --bpy-self-check "%~dp0SELF-CHECK.json" > "%~dp0SELF-CHECK.log" 2>&1\r\nset "check_result=%ERRORLEVEL%"\r\necho Self-check exit code: %check_result%\r\necho Please send SELF-CHECK.json and SELF-CHECK.log back.\r\npause\r\nexit /b %check_result%\r\n', encoding='utf-8')
    (destination/'README.txt').write_text('EXPERIMENT ONLY: standalone bpy 5.2.2, CPython 3.13.\nExtract the entire ZIP to a writable folder on Windows x64. Double-click RunSelfCheck.cmd. No installed Python or Blender is required. Send SELF-CHECK.json and SELF-CHECK.log. Then optionally launch the EXE and select your own PSP base PAC. No game assets are included.\nThe self-check tests procedural decimation, protected anatomy, UV/color/weight export, unit normals, native synthetic vectors and GUI/drag-drop. It does not test PPSSPP or prove every conversion is correct. Hosted CI is not a clean Windows installation; please record Windows version and whether Python/Blender is installed.\nThis prototype deliberately has a console for diagnostics. Production converter is unchanged.\nBlender/bpy is GPL; official COPYING, third-party notices and matching Blender source are included. Converter source is included. The repository currently has no explicit project license: importing GPL bpy into the app changes the licensing boundary. Production redistribution needs project licensing and GPL/source completeness review; this bundle does not declare that issue resolved.\n', encoding='utf-8')
    for p in destination.rglob('*'):
        if p.suffix.lower() in ('.pac', '.yobj', '.gim', '.png', '.obj') and 'bpy' not in p.parts:
            raise RuntimeError('Unexpected game-format/image asset: '+str(p))
    info = json.loads(__import__('urllib.request', fromlist=['urlopen']).urlopen('https://pypi.org/pypi/bpy/5.2.2/json').read())
    wheel = next(p for p in info['urls'] if p['filename'].endswith('win_amd64.whl'))
    files = {p.relative_to(destination).as_posix(): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
             for p in destination.rglob('*') if p.is_file()}
    manifest = dict(bpy='5.2.2', python=sys.version, upstream_wheel=wheel,
        blender_source_sha256=hashlib.file_digest(source.open('rb'), 'sha256').hexdigest(), files=files)
    (destination/'MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    try: build()
    except Exception:
        import traceback
        print('::error title=bpy build::'+traceback.format_exc().replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D'))
        raise
