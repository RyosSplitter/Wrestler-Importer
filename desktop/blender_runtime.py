"""Runtime discovery shared by Creator features and the converter."""
import os
from pathlib import Path
import subprocess
import sys


def resolve(explicit=None, *, shared=True):
    if explicit:
        paths=[Path(explicit)]
    elif getattr(sys,'frozen',False):
        root=Path(sys.executable).parent
        paths=[root/'runtime/blender/blender.exe']
        if shared:paths.append(root.parent/'PSP-Model-Suite/runtime/blender/blender.exe')
    else:
        paths=[Path(os.environ.get('PS2PSP_DEV_BLENDER','/usr/bin/blender'))]
    for path in paths:
        if path.is_file():return path.resolve()
    raise ValueError('Choose Blender 4.3.2 from your installed PSP Model Suite runtime/blender folder.')


def version(path):
    result=subprocess.run([str(path),'--version'],capture_output=True,text=True,timeout=20,
                          creationflags=0x08000000 if os.name=='nt' else 0,check=True)
    first=result.stdout.splitlines()[0]
    if first!='Blender 4.3.2':raise ValueError('Morph Studio currently validates Blender 4.3.2; selected runtime: '+first)
    return first
