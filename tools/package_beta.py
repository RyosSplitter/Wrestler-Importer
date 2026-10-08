"""Package the Windows launcher app with the user-supplied reference assets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def package(base, reference, baseline_bundle, output):
    from app.pipeline import verify_backend
    profile = verify_backend()
    for path, key in ((base, 'base_sha256'), (reference, 'reference_sha256')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != profile['sample'][key]:
            raise ValueError('Use the supplied references for the pinned beta package')
    prefix = 'WrestlerImporterBeta/'
    files = {}
    for directory in ('app', 'stable_pipeline'):
        for file in (ROOT / directory).iterdir():
            if file.suffix in ('.py', '.json'):
                files[prefix+directory+'/'+file.name] = file.read_bytes()
    for name in ('wrestler_beta.py', 'requirements-beta.txt', 'Start Wrestler Importer.cmd'):
        data = (ROOT / name).read_bytes()
        if name.endswith('.cmd'):
            data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        files[prefix+name] = data
    files[prefix+'README-beta.md'] = (ROOT / 'docs/windows-beta.md').read_bytes()
    files[prefix+'assets/Kurt-Angle-Ring.PAC'] = base.read_bytes()
    files[prefix+'assets/Full Body.yobj'] = reference.read_bytes()
    with zipfile.ZipFile(baseline_bundle) as z:
        pac = z.read('RVD-HCTP-to-PSP-opacity-fix-test.pac')
        if hashlib.sha256(pac).hexdigest() != profile['sample']['pac_sha256']:
            raise ValueError('The package baseline differs from the uploaded working PAC')
        files[prefix+'baseline/RVD-HCTP-to-PSP-opacity-fix-test.pac'] = pac
        for name in z.namelist():
            if name.startswith('preview/') and Path(name).suffix in ('.yobj', '.dae', '.png', '.gim'):
                if '..' in Path(name).parts:
                    raise ValueError('Unsafe preview archive path')
                files[prefix+'baseline/'+name] = z.read(name)
    manifest = {name.removeprefix(prefix): {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in files.items()}
    files[prefix+'package-manifest.json'] = (json.dumps(manifest, indent=2)+'\n').encode('utf-8')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:
            raise ValueError('Beta archive verification failed')
    return {'output': str(output), 'bytes': output.stat().st_size, 'files': len(files)}


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'reference', 'baseline-bundle', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.base, args.reference, args.baseline_bundle, args.output), indent=2))
