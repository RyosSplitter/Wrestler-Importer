"""Per-user preferences and reviewed export; never write into source/base PACs."""
import json
import os
from pathlib import Path
import tempfile
from desktop.core import digest,validate_pac

def data_dir():
    root=Path(os.environ.get('PS2PSP_DATA',Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'PS2PSP Pac Converter'))
    root.mkdir(parents=True,exist_ok=True);return root

def load_settings():
    try:
        value=json.loads((data_dir()/'settings.json').read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def save_settings(settings):
    root=data_dir();fd,tmp=tempfile.mkstemp(prefix='settings-',suffix='.tmp',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(json.dumps(settings,indent=2)+'\n')
        os.replace(tmp,root/'settings.json')
    finally:
        if Path(tmp).exists():Path(tmp).unlink()

def save_as(result,destination):
    """Check the immutable reviewed candidate again, then atomically copy it."""
    candidate=Path(result['pac']);destination=Path(destination)
    if destination.suffix.lower()!='.pac':raise ValueError('Save the output with a .pac extension.')
    if destination.resolve() in {Path(result[k]).resolve() for k in ('source','base','pac')}:raise ValueError('Save As cannot overwrite the source, PSP base or review candidate.')
    if destination.exists() and any(os.path.samefile(destination,result[k]) for k in ('source','base','pac')):raise ValueError('Save As points to a protected input through a hard link.')
    if digest(candidate)!=result['sha256']:raise ValueError('Review candidate changed; export withheld.')
    if result.get('adaptive_textures'):
        from desktop.texture_optimizer.candidates import read_gim
        validate_pac(candidate.read_bytes(),gim_reader=read_gim)
    else:validate_pac(candidate.read_bytes())
    previous=None
    if destination.exists():
        previous=digest(destination);backups=destination.parent/'.ps2psp-backups';backups.mkdir(exist_ok=True)
        backup=backups/(previous+'.pac')
        if not backup.exists():
            try:
                with backup.open('xb') as f:f.write(destination.read_bytes());f.flush();os.fsync(f.fileno())
            except FileExistsError:pass
        if digest(backup)!=previous:raise ValueError('Previous PAC backup verification failed; export withheld.')
    fd,temp=tempfile.mkstemp(prefix='.ps2psp-',suffix='.tmp',dir=destination.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(candidate.read_bytes());f.flush();os.fsync(f.fileno())
        if digest(temp)!=result['sha256']:raise ValueError('Copy verification failed.')
        if previous is not None and digest(destination)!=previous:raise ValueError('Destination changed during Save As; export withheld.')
        os.replace(temp,destination)
    finally:
        if Path(temp).exists():Path(temp).unlink()
    return str(destination)
