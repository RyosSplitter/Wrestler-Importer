"""Build a verified overlay update between two manifest-audited suite builds.

App files only, never PAC packaging. No removals or guessed runtime compatibility:
unchanged files must have identical old/new SHA-256 manifests; changes are copied
from the new tested build. The complete previous ZIP hash is checked first.
"""
import hashlib
import json
from pathlib import Path,PurePosixPath
import zipfile


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def safe_name(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value:raise ValueError('Unsafe manifest path')
    return value


def build(previous,new_folder,output,expected_previous_sha256):
    previous,new_folder,output=map(Path,(previous,new_folder,output))
    if output.exists():raise FileExistsError(output)
    if digest(previous)!=expected_previous_sha256:raise ValueError('Previous release checksum mismatch')
    root='PSP-Model-Suite/'
    current=json.loads((new_folder/'MANIFEST.json').read_text(encoding='utf-8'))
    changed=[];unchanged=[]
    with zipfile.ZipFile(previous) as old:
        before=json.loads(old.read(root+'MANIFEST.json'))
        removed=sorted(set(before['files'])-set(current['files']))
        if removed:raise ValueError('Overlay updates cannot remove old files: '+', '.join(removed[:15]))
        for name,expected in current['files'].items():
            safe_name(name);path=new_folder/name
            if path.is_symlink() or digest(path)!=expected:raise ValueError('New build manifest mismatch: '+name)
            if before['files'].get(name)==expected:
                old.getinfo(root+name);unchanged.append(name)
            else:changed.append(name)
    report=dict(from_version='0.27.0',to_version='0.27.1',previous_zip_sha256=expected_previous_sha256,
        new_manifest_sha256=digest(new_folder/'MANIFEST.json'),changed_files=changed,
        unchanged_file_count=len(unchanged),unchanged_files_have_identical_manifest_hashes=True,
        changed_uncompressed_bytes=sum((new_folder/n).stat().st_size for n in changed))
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as out:
        for name in changed+['MANIFEST.json']:out.write(new_folder/name,root+name)
        out.writestr('UPDATE-INFO.json',json.dumps(report,indent=2)+'\n')
        out.writestr('INSTALL-UPDATE.txt',
            'PSP Model Suite 0.27.0 -> 0.27.1 update\n\n'
            'For the complete v0.27.0 Windows x64 portable app only.\n'
            'Close the app. Keep a backup of your old app folder.\n'
            'Extract this ZIP into the parent folder of PSP-Model-Suite and allow\n'
            'the existing PSP-Model-Suite folder/files to be updated. If you\n'
            'renamed the app folder, copy the CONTENTS of this ZIP\'s\n'
            'PSP-Model-Suite folder into your app folder instead.\n'
            'Do not create a second nested PSP-Model-Suite folder.\n'
            'Keep your existing runtime, _internal, sources and licenses folders.\n'
            'Launch PSP-Model-Suite.exe normally. Preferences and PACs are not\n'
            'included in this update. New installs must use the full v0.27.1 ZIP.\n')
    report.update(zip_bytes=output.stat().st_size,sha256=digest(output))
    Path(str(output)+'.sha256').write_text(report['sha256']+'  '+output.name+'\n',encoding='ascii')
    return report


if __name__=='__main__':
    import sys
    print(json.dumps(build(*sys.argv[1:]),indent=2))
