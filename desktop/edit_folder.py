"""Portable, texture-editable PAC projects; native model records stay authoritative."""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile

import numpy as np
from PIL import Image

from desktop.workspace import digest, dump, inspect_workspace, verified_snapshot
from desktop.texture_optimizer.candidates import read_gim
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import replace_sections
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress, decompress

SCHEMA = 'psp-model-suite.edit-folder/1'


def publish_new(path, data):
    """Publish a complete checked file without overwriting an existing target."""
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.psp-pack-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if digest(Path(name).read_bytes())!=digest(data):
            raise ValueError('Output copy verification failed.')
        if os.name=='nt':
            # Windows rename fails if the destination exists, including FAT/exFAT.
            os.rename(name,path)
        else:
            os.link(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def png_path(row):
    name = re.sub('[^A-Za-z0-9_-]', '_', row['name'])[:48] or 'texture'
    return f"textures/{row['index']:04d}-{name}.png"


def editable(row):
    return row['section']==9 and row['name'].casefold() not in ('blood', 'blood_b', 'bandage') and row['png'] is not None


def export_folder(manifest_path, destination):
    """Create a new self-contained folder; never merge into an existing project."""
    manifest, original = verified_snapshot(manifest_path)
    source, destination = Path(manifest_path).parent, Path(destination)
    if destination.exists():
        raise FileExistsError('Export requires a new folder; the existing folder was not changed.')
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError('Export outside the temporary inspection workspace.')
    if any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('Unexpected symbolic link in workspace.')
    shutil.copytree(source, destination)
    # Friendly texture filenames remain deterministic and cannot contain paths.
    for row in manifest['textures']:
        if row['png']:
            old = row['png']
            new = png_path(row)
            (destination/old).rename(destination/new)
            for model in manifest['models']:
                mtl = destination/Path(model['yobj']).parent/'preview.mtl'
                if mtl.exists():
                    mtl.write_text(mtl.read_text(encoding='ascii').replace('../../'+old, '../../'+new), encoding='ascii')
            row['png'] = new
        row['editable'] = editable(row)
    dump(destination/'manifest.json', manifest)
    project = dict(schema=SCHEMA, source=manifest['source'], source_name=Path(manifest['source']).name, source_sha256=digest(original),
                   source_bytes=len(original), texture_editing_only=True,
                   max_pac_bytes=max(IN_RING_MAX_PAC_BYTES, len(original)),
                   budget_policy=f'{IN_RING_MAX_PAC_BYTES}-byte conversion envelope, or the larger existing native PAC size; no runtime texture allocation increase')
    if manifest.get('native_descriptor_arrays'):project['native_descriptor_arrays']=True
    dump(destination/'project.json', project)
    with (destination/'textures.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['native_name', 'section', 'png', 'editable', 'width', 'height', 'palette_entries'])
        for row in manifest['textures']:
            writer.writerow([row['name'], row['section'], row['png'], row['editable'],
                             row.get('width'), row.get('height'), row.get('palette_entries')])
    (destination/'README.txt').write_text(
        'PSP Model Suite editable folder\n\n'
        'Edit the named PNGs in textures/ using Photoshop, GIMP or another image editor.\n'
        'Save as PNG with the SAME dimensions and filenames. Use sRGB color values.\n'
        'textures.csv identifies native names, dimensions, palette capacities and editable maps.\n'
        'The packer retains the original 16/256-entry palette capacity; new colors may be quantized.\n'
        'Alpha is preserved exactly or packing stops. No automatic resizing or geometry reduction occurs.\n\n'
        'Back in Model Editor, choose Pack folder and select THIS folder. Save a new PAC in your PAC library.\n'
        'The original game/source PAC is not needed to reopen or pack this self-contained folder.\n'
        'original.pac is the authoritative snapshot: do not edit it or project.json.\n'
        'models/ includes native YOBJ, OBJ/MTL and views for preview. Geometry/material/UV reimport\n'
        'is not supported yet; changing those files makes packing stop rather than ignoring changes.\n'
        'Raw encoded texture files and effect/blood-stage PNGs are read-only in this version.\n'
        'PSD/XCF working files may be kept beside PNGs; only the listed PNGs are imported.\n'
        'Unedited PNG pixels preserve their original encoded GIM bytes. A fully unedited project\n'
        'produces an exactly identical PAC, including original compression and padding.\n'
        'Edited outputs still need SVR/PPSSPP testing.\n', encoding='utf-8')
    return str(destination)


def quantize_rgba(rgba, original_palette):
    """Fixed native palette capacity with exact per-pixel alpha, never RGBA averaging."""
    capacity = len(original_palette)
    colors, inverse = np.unique(rgba.reshape(-1, 4), axis=0, return_inverse=True)
    palette = original_palette.copy()
    if len(colors)<=capacity:
        palette[:len(colors)] = colors
        return inverse.reshape(rgba.shape[:2]).astype(np.uint8), palette, 'Exact RGBA'
    levels, counts = np.unique(rgba[:,:,3], return_counts=True)
    if len(levels)>capacity:
        raise ValueError(f'PNG has {len(levels)} alpha levels but the native palette holds {capacity}; simplify alpha without changing dimensions.')
    allocations = np.ones(len(levels), dtype=int)
    unique_counts = [len(np.unique(rgba[rgba[:,:,3]==level,:3], axis=0)) for level in levels]
    for _ in range(capacity-len(levels)):
        eligible = [i for i in range(len(levels)) if allocations[i]<unique_counts[i]]
        if not eligible:
            break
        chosen = max(eligible, key=lambda i: counts[i]/(allocations[i]+1))
        allocations[chosen] += 1
    best = None
    for method in (Image.Quantize.MEDIANCUT, Image.Quantize.MAXCOVERAGE, Image.Quantize.FASTOCTREE):
        pixels = np.zeros(rgba.shape[:2], dtype=np.uint8)
        palette = original_palette.copy()
        start = 0
        for level, count in zip(levels, allocations):
            mask = rgba[:,:,3]==level
            values = rgba[mask,:3]
            encoded = Image.fromarray(values[None,:,:], 'RGB').quantize(colors=int(count), method=method, dither=Image.Dither.NONE)
            ids = np.asarray(encoded, dtype=np.uint8).reshape(-1)
            table = np.asarray(encoded.getpalette(), dtype=np.uint8).reshape(-1, 3)
            palette[start:start+count,:3] = table[:count]
            palette[start:start+count,3] = level
            pixels[mask] = ids+start
            start += count
        loss = float(((palette[pixels][:,:,:3].astype(float)-rgba[:,:,:3])**2 * (rgba[:,:,3:4]/255)).mean())
        if best is None or loss<best[0]:
            best = loss, pixels, palette, method.name+' / exact alpha groups'
    return best[1:]


def replace_gim_pixels(original, rgba):
    """Patch only pixels/CLUT in a verified existing GIM; keep all header/padding bytes."""
    old_pixels, old_colors = read_gim(original)
    if rgba.shape != (*old_pixels.shape, 4) or rgba.dtype!=np.uint8:
        raise ValueError('Edited PNG dimensions must match the original texture.')
    if np.array_equal(rgba, old_colors[old_pixels]):
        return original, dict(changed=False)
    pixels, colors, method = quantize_rgba(rgba, old_colors)
    if not np.array_equal(colors[pixels][:,:,3], rgba[:,:,3]):
        raise ValueError('Alpha preservation check failed.')
    h,w = pixels.shape
    bits = 4 if len(colors)==16 else 8
    if bits==4 and w%2:
        raise ValueError('Unimplemented odd-width native texture.')
    pitch = ((w*bits+7)//8+15)//16*16
    ph = (h+7)//8*8
    end = 48+struct.unpack_from('<I', original, 52)[0]
    y,x = np.indices((ph,pitch))
    addresses = ((y//8)*(pitch//16)+x//16)*128+(y%8)*16+x%16
    raw = bytearray(original)
    buffer = np.frombuffer(raw, np.uint8, count=end-128, offset=128)
    plane = buffer[addresses].copy()
    if bits==8:
        plane[:h,:w] = pixels
    else:
        plane[:h,:w//2] = pixels[:,::2] | (pixels[:,1::2]<<4)
    buffer[addresses] = plane
    raw[end+80:] = colors.tobytes()
    result = bytes(raw)
    p,c = read_gim(result)
    if not np.array_equal(p,pixels) or not np.array_equal(c,colors):
        raise ValueError('Encoded texture round trip failed.')
    reconstructed = c[p]
    return result, dict(changed=True, dimensions=[w,h], palette_entries=len(colors),
                        useful_png_colors=len(np.unique(rgba.reshape(-1,4),axis=0)),
                        quantizer=method, alpha_exact=True,
                        rgb_rmse=float(np.sqrt(np.mean((reconstructed[:,:,:3].astype(float)-rgba[:,:,:3])**2))),
                        serialized_bytes=len(result), allocation_unchanged=len(result)==len(original))


def pack_folder(project_folder, destination):
    folder, destination = Path(project_folder).resolve(), Path(destination).resolve()
    project = json.loads((folder/'project.json').read_text(encoding='utf-8'))
    if project.get('schema')!=SCHEMA:
        raise ValueError('Select a PSP Model Suite editable folder containing project.json.')
    if destination.suffix.casefold()!='.pac' or destination.exists():
        raise ValueError('Choose a NEW .pac filename; existing files are never overwritten.')
    report_path = destination.with_name(destination.name+'.report.json')
    if report_path.exists():
        raise FileExistsError('A report already exists for this filename; choose a new PAC filename.')
    if destination==Path(project['source']).resolve() or destination.is_relative_to(folder):
        raise ValueError('Save the rebuilt PAC outside the edit folder, using a new filename in your PAC library.')
    original = (folder/'original.pac').read_bytes()
    if digest(original)!=project['source_sha256']:
        raise ValueError('The original PAC snapshot changed; packing withheld.')
    # Rebuild the inventory from native bytes, never trust editable JSON offsets,
    # model counts, palette capacities or file mappings supplied by a project.
    with tempfile.TemporaryDirectory(prefix='psp-edit-check-') as temp:
        reference = Path(temp)/'reference'
        baseline = inspect_workspace(folder/'original.pac', reference, resolution=64, native_descriptor_arrays=project.get('native_descriptor_arrays') is True)
        if any(m['error'] for m in baseline['models']):
            raise ValueError('A native model is outside the verified PSP reader; texture repacking is withheld.')
        expected_geometry = set()
        for model in baseline['models']:
            model_folder = Path(model['yobj']).parent
            for name in ('model.yobj','model.obj','preview.mtl'):
                relative = model_folder/name
                expected_geometry.add(relative.as_posix())
                expected = (reference/relative).read_bytes()
                if name=='preview.mtl':
                    text = expected.decode('ascii')
                    for row in baseline['textures']:
                        if row['png']:
                            text = text.replace('../../'+row['png'], '../../'+png_path(row))
                    expected = text.encode('ascii')
                actual = (folder/relative).read_bytes()
                if name=='preview.mtl':
                    actual = actual.replace(b'\r\n', b'\n')
                    expected = expected.replace(b'\r\n', b'\n')
                if actual!=expected:
                    raise ValueError(f'{relative} was modified. Geometry, UV and material edits are not supported yet; edit texture PNGs only.')
        for path in folder.rglob('*'):
            if path.is_symlink():
                raise ValueError('Symbolic links are not supported in editable folders.')
            if path.suffix.casefold() in ('.obj','.yobj','.mtl') and path.relative_to(folder).as_posix() not in expected_geometry:
                raise ValueError('Additional model/material file cannot be imported: '+str(path.relative_to(folder)))
        unpacked = {s['id']:(s,raw) for s,raw in sections(original)}
        if len(unpacked)!=len(baseline['sections']):
            raise ValueError('Duplicate native section IDs are unsupported.')
        changed_tables = {}
        texture_report = []
        png_snapshots = {}
        for row in baseline['textures']:
            if (folder/row['raw']).read_bytes()!=(reference/row['raw']).read_bytes():
                raise ValueError('Raw encoded texture was modified; edit its named PNG instead: '+row['name'])
            if not row['png']:
                continue
            path = folder/png_path(row)
            png_bytes = path.read_bytes()
            png_snapshots[path] = digest(png_bytes)
            with Image.open(io.BytesIO(png_bytes)) as image:
                if image.format!='PNG':
                    raise ValueError(path.name+': save the edited image as PNG.')
                if image.size!=(row['width'],row['height']):
                    raise ValueError(f"{path.name}: keep the original {row['width']}×{row['height']} dimensions.")
                rgba = np.asarray(image.convert('RGBA'))
            raw = (reference/row['raw']).read_bytes()
            if not editable(row):
                p,c = read_gim(raw)
                if not np.array_equal(rgba,c[p]):
                    raise ValueError(row['name']+': effect/blood-stage or non-main texture is read-only in this version.')
                continue
            encoded, report = replace_gim_pixels(raw, rgba)
            texture_report.append(dict(name=row['name'], file=png_path(row), section=row['section'], **report))
            if encoded!=raw:
                table = changed_tables.setdefault(row['section'], bytearray(unpacked[row['section']][1]))
                records = parse_textures(table)
                matches = [t for t in records if t['name']==row['name']]
                if len(matches)!=1:
                    raise ValueError('Ambiguous native texture name: '+row['name'])
                record = matches[0]
                if len(encoded)!=record['size']:
                    raise ValueError('Texture allocation changed unexpectedly.')
                table[record['offset']:record['offset']+record['size']] = encoded
        replacements = {}
        for section, table in changed_tables.items():
            stored = unpacked[section][0]
            previous = original[stored['offset']:stored['offset']+stored['size']]
            raw = bytes(table)
            if previous.startswith(b'BPE '):
                encoded = min((compress(raw),compress(raw,max_distinct=220)), key=len)
                if decompress(encoded)!=raw:
                    raise ValueError('Changed texture table compression failed.')
            else:
                encoded = raw
            replacements[section] = encoded
        if replacements:
            # Do not discard unclassified nonzero gap/trailer data during repacking.
            info = inspect_pac(original)
            cursor = info['payload_start']
            for section in sorted(info['sections'],key=lambda s:s['offset']):
                if any(original[cursor:section['offset']]):
                    raise ValueError('Nonzero data outside declared sections requires separate format analysis.')
                cursor = section['offset']+section['size']
            if any(original[cursor:]):
                raise ValueError('Nonzero trailing PAC data cannot be discarded safely.')
            candidate = replace_sections(original, replacements)
        else:
            candidate = original
        final = inspect_pac(candidate)
        budget = max(IN_RING_MAX_PAC_BYTES,len(original))
        if len(candidate)>budget:
            raise ValueError(f'Edited PAC is {len(candidate):,} bytes, over its {budget:,}-byte budget. No PAC written; simplify texture colors in the editor.')
        decoded_final = {s['id']:(s,raw) for s,raw in sections(candidate)}
        if [s['id'] for s in final['sections']]!=[s['id'] for s in baseline['sections']]:
            raise ValueError('PAC section order changed.')
        for section,(before,raw) in unpacked.items():
            after, decoded = decoded_final[section]
            if section not in replacements:
                if after['sha256']!=before['sha256'] or decoded!=raw:
                    raise ValueError('Unrelated PAC payload changed.')
            elif decoded!=bytes(changed_tables[section]):
                raise ValueError('Final texture payload differs from the validated table.')
        if replacements and (len(candidate)%2048 or any(s['offset']%16 for s in final['sections'])):
            raise ValueError('Final PAC alignment failed.')
        if (folder/'original.pac').read_bytes()!=original:
            raise ValueError('Snapshot changed during packing.')
        for path,sha in png_snapshots.items():
            if digest(path.read_bytes())!=sha:
                raise ValueError(path.name+' changed during packing; finish saving the texture and pack again.')
        report = dict(pac=str(destination), sha256=digest(candidate), bytes=len(candidate), original_bytes=len(original),
                      max_pac_bytes=budget, textures=texture_report, changed_textures=sum(t['changed'] for t in texture_report),
                      changed_sections=sorted(replacements), all_model_payloads_exact=True,
                      unrelated_stored_sections_exact=True, texture_allocation_unchanged=True,
                      unedited_round_trip_exact=candidate==original,
                      report_path=str(report_path),
                      status='Native structure/preservation checked; edited appearance still requires PPSSPP testing.')
        # Exclusive write is last: rejected/oversized candidates leave no output.
        report_created = False
        try:
            publish_new(report_path,(json.dumps(report,indent=2)+'\n').encode('utf-8'))
            report_created = True
            publish_new(destination,candidate)
        except (OSError,ValueError):
            if report_created:
                report_path.unlink(missing_ok=True)
            raise
        return report
