"""Read-only PSP workspace. Native bytes, not OBJ, are the authoritative model.

Inspection never runs conversion, rewrites a YOBJ or normalizes a PAC. Unknown
layouts remain explicit findings. Generated filenames never use embedded names.
"""
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from PIL import Image

from desktop.preview import VIEWS, render
from desktop.texture_optimizer.candidates import read_gim
from tools.pac_inspect import inspect_pac, parse_textures
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import write_preview
from tools.yukes_bpe import decompress

SCHEMA = 'psp-model-suite.workspace/1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def inspect_workspace(source, output, *, resolution=512, native_descriptor_arrays=False):
    reader=audit_yobj
    if native_descriptor_arrays:
        from model_creator.native import audit_yobj as reader
    source, output = Path(source).resolve(), Path(output)
    if not 64 <= resolution <= 1024:
        raise ValueError('Preview resolution must be between 64 and 1024.')
    if output.exists():
        raise FileExistsError('Choose a new workspace directory.')
    data = source.read_bytes()
    container = inspect_pac(data)
    output.mkdir(parents=True)
    (output/'original.pac').write_bytes(data)
    (output/'textures').mkdir()
    manifest = dict(schema=SCHEMA, source=str(source), source_sha256=digest(data),
                    bytes=len(data), snapshot='original.pac', models=[], textures=[],
                    sections=[], findings=[], conversion_budget_bytes=148000,
                    within_conversion_budget=len(data)<=148000,
                    game_compatibility='Not established by structural inspection.',
                    geometry_or_skinning_modified=False)
    if native_descriptor_arrays:manifest['native_descriptor_arrays']=True
    # Preserve each section verbatim, including compressed streams and opaque data.
    unpacked = []
    for section in container['sections']:
        raw = data[section['offset']:section['offset']+section['size']]
        record = {k: section[k] for k in ('index', 'id', 'offset', 'size', 'sha256')}
        record.update(compressed=raw.startswith(b'BPE '), decoded_bytes=None)
        manifest['sections'].append(record)
        try:
            decoded = decompress(raw) if record['compressed'] else raw
            record['decoded_bytes'] = len(decoded)
            unpacked.append((section, decoded))
        except (ValueError, IndexError, struct.error) as exc:
            manifest['findings'].append(f"Section {section['id']} cannot be decoded: {exc}")
    for section, raw in unpacked:
        if len(raw)<16 or raw[4:16] != struct.pack('<3I', 0x100, 0, 16):
            continue
        for entry in parse_textures(raw):
            index = len(manifest['textures'])
            stem = 'textures/texture_%04d' % index
            image = raw[entry['offset']:entry['offset']+entry['size']]
            row = dict(index=index, section=section['id'], section_index=section['index'],
                       name=entry['name'], bytes=len(image), sha256=digest(image),
                       raw=stem+'.bin', png=None, error=None)
            (output/row['raw']).write_bytes(image)
            try:
                pixels, colors = read_gim(image)
                rgba = colors[pixels]
                row.update(png=stem+'.png', width=pixels.shape[1], height=pixels.shape[0],
                           palette_entries=len(colors), used_colors=len(set(map(bytes, rgba.reshape(-1, 4)))),
                           alpha=bool((rgba[:,:,3]!=255).any()))
                Image.fromarray(rgba).save(output/row['png'])
            except (ValueError, IndexError, struct.error) as exc:
                row['error'] = str(exc)
                manifest['findings'].append(f"Texture {entry['name']!r} in section {section['id']}: {exc}")
            manifest['textures'].append(row)
    for section, raw in unpacked:
        if not raw.startswith(b'YOBJ'):
            continue
        number = len(manifest['models'])
        folder = output/'models'/('model_%04d' % number)
        folder.mkdir(parents=True)
        row = dict(index=number, section=section['id'], section_index=section['index'],
                   yobj=str((folder/'model.yobj').relative_to(output)).replace('\\', '/'),
                   sha256=digest(raw), bytes=len(raw), error=None, views={}, preview_error=None)
        (folder/'model.yobj').write_bytes(raw)
        manifest['models'].append(row)
        try:
            model = reader(raw)
        except (ValueError, IndexError, struct.error) as exc:
            row['error'] = str(exc)
            manifest['findings'].append(f"Model in section {section['id']} is outside the verified PSP reader: {exc}")
            continue
        row.update(name=model['report']['model_name'], meshes=model['report']['meshes'],
                   vertices=model['report']['vertices'], triangles=model['report']['triangles'],
                   bones=len(model['bones']), textures=model['texture_names'],
                   audit=str((folder/'audit.json').relative_to(output)).replace('\\', '/'))
        dump(output/row['audit'], model['report'])
        # Keep material identity local to each model. Texture names are metadata,
        # never paths; prefer the observed main section, otherwise require unique.
        mapped = {}
        for name in model['texture_names']:
            # Observed native PAC tables use upper-case spellings while YOBJ
            # references use lower case (for example KA_FACE / ka_face).
            choices = [t for t in manifest['textures'] if t['name'].casefold()==name.casefold()]
            main = [t for t in choices if t['section']==9]
            chosen = main if main else choices
            if len(chosen)==1 and chosen[0]['png']:
                mapped[name] = chosen[0]
            else:
                manifest['findings'].append(f"Model {number}: missing, ambiguous or unsupported texture {name!r}.")
        write_preview(model, folder/'model.obj')
        mtl = []
        for i, name in enumerate(model['texture_names']):
            mtl += ['newmtl texture_%d' % i, 'Kd 1 1 1', 'Ks 0 0 0']
            if name in mapped:
                mtl += ['map_Kd ../../'+mapped[name]['png']]
        (folder/'preview.mtl').write_text('\n'.join(mtl)+'\n', encoding='ascii')
        if len(mapped) != len(model['texture_names']):
            row['preview_error'] = 'Preview withheld because required textures could not be resolved.'
            continue
        try:
            textures = {name: (output/t['raw']).read_bytes() for name,t in mapped.items()}
            for view in VIEWS:
                path = folder/(view+'.png')
                render(model, textures, view, resolution, gim_reader=read_gim).save(path)
                row['views'][view] = str(path.relative_to(output)).replace('\\', '/')
        except (ValueError, IndexError, struct.error) as exc:
            row['preview_error'] = str(exc)
            manifest['findings'].append(f"Model {number} preview: {exc}")
    if not manifest['models']:
        raise ValueError('No YOBJ model found. This editor currently opens native PSP wrestler PACs.')
    try:
        from desktop.core import validate_pac
        validate_pac(data, max_bytes=max(len(data), 148000), gim_reader=read_gim)
        manifest['converter_export_profile'] = dict(passed=True, error=None)
    except (ValueError, KeyError, IndexError, struct.error) as exc:
        manifest['converter_export_profile'] = dict(passed=False, error=str(exc))
        manifest['findings'].append('Converter export-profile check: '+str(exc))
    if source.read_bytes()!=data:
        raise ValueError('Source changed during inspection; discard this workspace and reopen it.')
    dump(output/'manifest.json', manifest)
    return manifest


def verified_snapshot(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema') != SCHEMA or manifest.get('snapshot')!='original.pac':
        raise ValueError('Unsupported workspace manifest.')
    data = (manifest_path.parent/'original.pac').read_bytes()
    if digest(data)!=manifest['source_sha256']:
        raise ValueError('Workspace snapshot changed; export withheld.')
    return manifest, data


def copy_original(manifest_path, destination):
    """Byte-exact copy, not a model rebuild or a compatibility certification."""
    manifest, data = verified_snapshot(manifest_path)
    destination = Path(destination)
    if destination.suffix.lower()!='.pac':
        raise ValueError('Use a .pac extension.')
    if destination.resolve()==Path(manifest['source']).resolve():
        raise ValueError('Cannot overwrite the original input.')
    # Exclusive creation also rejects hard links, symlinks and accidental overwrite.
    with destination.open('xb') as stream:
        stream.write(data)
    if digest(destination.read_bytes())!=manifest['source_sha256']:
        raise ValueError('Copied PAC checksum differs from the workspace snapshot.')
    return str(destination)


def export_previews(manifest_path, destination):
    """Export native YOBJ/audits plus OBJ/MTL/PNG; OBJ is preview-only."""
    manifest, _ = verified_snapshot(manifest_path)
    root, destination = Path(manifest_path).parent, Path(destination)
    # Include only known generated paths, never follow names from the input PAC.
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('README.txt', 'Native YOBJ retains the original PSP records. The PAC snapshot stays in the local workspace.\n'
                         'OBJ is a rest-geometry preview and does not retain skinning or PSP metadata.\n'
                         'No OBJ reimport is supported in this milestone.\n')
        archive.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
        for directory in ('models', 'textures'):
            for path in sorted((root/directory).rglob('*')):
                if path.is_symlink():
                    raise ValueError('Unexpected symbolic link in workspace export.')
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    return str(destination)
