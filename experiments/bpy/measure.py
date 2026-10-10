"""Measure the actual archive, including notices, source and native resources."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def measure(path):
    path = Path(path)
    groups = defaultdict(lambda: dict(compressed_bytes=0, expanded_bytes=0, files=0))
    with zipfile.ZipFile(path) as archive:
        files = [i for i in archive.infolist() if not i.is_dir()]
        for item in files:
            parts = Path(item.filename).parts[1:]
            if 'bpy' in parts and '_internal' in parts: key = 'bpy-runtime'
            elif parts and parts[0]=='runtime': key = 'full-blender-runtime'
            elif parts and parts[0]=='sources' and item.filename.endswith('.tar.xz'): key = 'blender-source'
            elif parts and parts[0]=='sources': key = 'converter-source-docs'
            elif parts and parts[0]=='licenses': key = 'notices'
            elif parts and parts[0]=='_internal': key = 'frozen-app-libraries'
            elif item.filename.endswith('.exe'): key = 'launcher'
            else: key = 'manifest-readme-selfcheck'
            row = groups[key]; row['compressed_bytes'] += item.compress_size
            row['expanded_bytes'] += item.file_size; row['files'] += 1
        compressed = sum(i.compress_size for i in files)
        return dict(filename=path.name, zip_bytes=path.stat().st_size,
            expanded_bytes=sum(i.file_size for i in files), files=len(files),
            zip_container_overhead_bytes=path.stat().st_size-compressed, groups=dict(groups),
            sha256=hashlib.file_digest(path.open('rb'), 'sha256').hexdigest())


if __name__=='__main__':
    print(json.dumps([measure(p) for p in sys.argv[1:]], indent=2))
