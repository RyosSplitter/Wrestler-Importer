"""Lower PSP GIM resolution without changing model sections or palettes."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections, texture_table
from .texture_convert import read_gim, write_gim4, write_gim8
from .yukes_bpe import compress, decompress


def smaller(width, height, bits):
    candidates = []
    if height >= 16:
        candidates.append((width, height//2))
    minimum_width = 32 if bits == 4 else 16
    if width >= minimum_width*2:
        candidates.append((width//2, height))
    if not candidates:
        return None
    # Prefer the least elongated valid image, retaining horizontal detail on
    # ties. Normalized UVs remain unchanged even for a rectangular texture.
    return min(candidates, key=lambda size: max(size)/min(size))


def reduce_textures(source, output, fraction=.5):
    if output.exists():
        raise FileExistsError(output)
    if not 0 < fraction < 1:
        raise ValueError('Texture fraction must be between zero and one')
    original = source.read_bytes()
    before = inspect_pac(original)
    section = next(s for s in before['sections'] if s['id'] == 9)
    stored = original[section['offset']:section['offset']+section['size']]
    table = decompress(stored) if stored.startswith(b'BPE ') else stored
    entries = []
    for entry in parse_textures(table):
        raw = table[entry['offset']:entry['offset']+entry['size']]
        indices, palette = read_gim(raw)
        bits = 4 if len(palette) == 16 else 8
        writer = write_gim4 if bits == 4 else write_gim8
        height, width = indices.shape
        size = smaller(width, height, bits)
        entries.append(dict(name=entry['name'], original_size=[width, height],
                            original_bytes=len(raw), size=size or (width, height),
                            indices=indices, palette=palette, writer=writer, bits=bits))

    def payload(entry):
        # Resample the existing index image. No palette regeneration, color
        # depth change, alpha processing or new colors are introduced.
        pixels = np.array(Image.fromarray(entry['indices']).resize(
            entry['size'], Image.Resampling.NEAREST), dtype=np.uint8)
        return entry['writer'](pixels, entry['palette']), pixels

    original_bytes = sum(e['original_bytes'] for e in entries)
    target = int(original_bytes*fraction)
    # Fixed palette/header overhead means half the pixels saves less than
    # half the file bytes. Take further valid resolution steps on body maps,
    # keeping face/eyes/teeth/hair until body options have been exhausted.
    protected = {'l-kao2', 'l-eye', 'kuchi01', 'ha', 'l_ude'}
    while sum(len(payload(e)[0]) for e in entries) > target:
        candidates = [e for e in entries if smaller(*e['size'], e['bits'])]
        if not candidates:
            raise ValueError('PSP block and palette minimums prevent this texture budget')
        candidates.sort(key=lambda e: (e['name'] in protected,
                                      -len(payload(e)[0]), e['name']))
        entry = candidates[0]
        entry['size'] = smaller(*entry['size'], entry['bits'])

    payloads = [payload(e)[0] for e in entries]
    updated_table = texture_table([e['name'] for e in entries], payloads)
    updated_stored = compress(updated_table) if stored.startswith(b'BPE ') else updated_table
    result = replace_sections(original, {9: updated_stored})
    after = inspect_pac(result)
    unchanged = []
    for s in after['sections']:
        assert s['offset'] % 16 == 0
        if s['id'] != 9:
            old = next(e for e in before['sections'] if e['id'] == s['id'])
            assert result[s['offset']:s['offset']+s['size']] == original[old['offset']:old['offset']+old['size']]
            unchanged.append(s['id'])
    if updated_stored.startswith(b'BPE '):
        assert decompress(updated_stored) == updated_table
    assert sum(map(len, payloads)) <= target
    assert source.read_bytes() == original

    output.mkdir(parents=True)
    preview = output/'preview'
    preview.mkdir()
    report_entries = []
    for entry, raw in zip(entries, payloads):
        indices, palette = read_gim(raw)
        expected_raw, expected_pixels = payload(entry)
        assert raw == expected_raw
        assert np.array_equal(indices, expected_pixels)
        assert np.array_equal(palette, entry['palette'])
        (preview/(entry['name']+'.gim')).write_bytes(raw)
        Image.fromarray(palette[indices]).save(preview/(entry['name']+'.png'))
        report_entries.append(dict(name=entry['name'], original_dimensions=entry['original_size'],
                                   dimensions=list(entry['size']), bits=entry['bits'],
                                   original_bytes=entry['original_bytes'], bytes=len(raw),
                                   rgba_palette_identical=True))
    model_section = next(e for e in before['sections'] if e['id'] == 2)
    model_stored = original[model_section['offset']:model_section['offset']+model_section['size']]
    model = decompress(model_stored) if model_stored.startswith(b'BPE ') else model_stored
    (preview/'prepared.yobj').write_bytes(model)
    pac = output/'1800-PSP-hybrid-half-textures.pac'
    pac.write_bytes(result)
    report = dict(original_pac_bytes=len(original), pac_bytes=len(result),
                  original_gim_bytes=original_bytes, gim_bytes=sum(map(len, payloads)),
                  texture_size_fraction=sum(map(len, payloads))/original_bytes,
                  original_texture_section_stored_bytes=len(stored),
                  texture_section_stored_bytes=len(updated_stored),
                  texture_section_expanded_bytes=len(updated_table),
                  unchanged_sections=unchanged, model_section_byte_identical=True,
                  model_expanded_sha256=hashlib.sha256(model).hexdigest(),
                  original_pac_sha256=hashlib.sha256(original).hexdigest(),
                  pac_sha256=hashlib.sha256(result).hexdigest(),
                  resampling='Nearest neighbor on existing palette indices',
                  palette_and_alpha_values_unchanged=True, textures=report_entries,
                  status='Experimental PSP candidate; PPSSPP validation pending')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(reduce_textures(args.source, args.output), indent=2))
