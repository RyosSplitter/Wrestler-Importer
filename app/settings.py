import json
import os
from pathlib import Path

from app.pipeline import ROOT


def data_dir():
    if os.environ.get('WRESTLER_IMPORTER_DATA'):
        return Path(os.environ['WRESTLER_IMPORTER_DATA'])
    parent = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.config')))
    return parent / 'WrestlerImporterBeta'


def defaults():
    assets = ROOT / 'assets'
    return {'source': '', 'base': str(assets / 'Kurt-Angle-Ring.PAC'),
            'reference': str(assets / 'Full Body.yobj'), 'editor': '',
            'blender': '', 'target_game': 'SVR 2011 PSP',
            'output_parent': str(Path.home() / 'Documents' / 'WrestlerImporterExports')}


def load():
    result = defaults()
    try:
        values = json.loads((data_dir() / 'settings.json').read_text(encoding='utf-8'))
        result.update({k: v for k, v in values.items() if k in result and isinstance(v, str)})
    except (OSError, ValueError, AttributeError):
        pass
    return result


def save(values):
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'settings.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({k: values[k] for k in defaults()}, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)
