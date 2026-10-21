"""Experimental lossless storage of the existing PSP effect texture table.

Do not delete effects or alter decoded assets to fit a texture budget. Native
SVR2011 references already store section 8 as BPE. This wrapper reuses existing
compression/packaging and proves every decoded section unchanged. Not enabled
in the production converter.
"""
import hashlib
from desktop.texture_optimizer.candidates import read_gim
from tools.pac_inspect import parse_textures
from tools.pac_repack import rewrite_sections
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress, decompress


def compact_effect_storage(data):
    old = list(sections(data))
    effect = next(((s, raw) for s, raw in old if s['id'] == 8), None)
    if effect is None:
        return data, dict(changed=False, reason='No effect section', all_decoded_sections_exact=True)
    section, raw = effect
    table = parse_textures(raw)
    if not table or any(row['extension'] != 'gim' for row in table):
        raise ValueError('Section 8 is not a verified GIM texture table')
    for row in table:
        read_gim(raw[row['offset']:row['offset'] + row['size']])
    stored = data[section['offset']:section['offset'] + section['size']]
    encoded = compress(raw)
    if decompress(encoded) != raw: raise ValueError('Effect table round trip failed')
    result = data if len(encoded) >= len(stored) else rewrite_sections(data, {8: encoded})
    new = list(sections(result))
    if [s['id'] for s, _ in old] != [s['id'] for s, _ in new]:
        raise ValueError('Section order changed')
    retained = []
    for (a, x), (b, y) in zip(old, new):
        if x != y: raise ValueError('Decoded asset changed')
        if a['id'] != 8:
            if data[a['offset']:a['offset'] + a['size']] != result[b['offset']:b['offset'] + b['size']]:
                raise ValueError('Unrelated stored payload changed')
            retained.append(a['id'])
    final = next(s for s, _ in new if s['id'] == 8)
    return result, dict(changed=result != data, section=8, decoded_bytes=len(raw),
                        decoded_sha256=hashlib.sha256(raw).hexdigest(),
                        stored_bytes_before=len(stored), stored_bytes_after=final['size'],
                        reclaimed_stored_bytes=len(stored) - final['size'],
                        all_decoded_sections_exact=True, other_stored_payloads_exact=retained,
                        effect_gim_hashes={row['name']: hashlib.sha256(raw[row['offset']:row['offset'] + row['size']]).hexdigest() for row in table},
                        compressor=dict(existing_codec=True, block_size=4000, max_distinct=200),
                        policy='BPE storage only; all effects, texture records and decoded bytes retained')
