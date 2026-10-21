"""Measured, sample-trial atlas allocation; no production texture-path changes."""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import json
from pathlib import Path

import numpy as np
from PIL import Image

from desktop.texture_optimizer.analysis import analyze, measure, model_usage, occupied
from desktop.texture_optimizer.candidates import encode, dimensions, read_gim, write_gim, OBSERVED_T8_DIMENSIONS
from tools.pac_inspect import parse_textures
from tools.psp_mesh_merge_trial import sections
from tools.pac_repack import texture_table, rewrite_sections
from tools.yukes_bpe import compress, decompress
from desktop.accessories import package_models


def encode_occupied(source, size, bits, color_limit, mask):
    """Train CLUT on UV-used colors, not unrelated atlas crop padding."""
    if size not in dimensions(source.shape[1], source.shape[0]) or np.any(source[:, :, 3] != 255):
        raise ValueError('Occupied encoder requires opaque, native-dimension, source-bounded input')
    target = np.array(Image.fromarray(source).resize(size, Image.Resampling.LANCZOS))
    occupied_mask = np.asarray(mask) > 0
    used = np.array(Image.fromarray(occupied_mask.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)) > 0
    if not used.any():
        raise ValueError('No occupied texels at candidate resolution')
    useful = len(np.unique(source[occupied_mask, :3], axis=0))
    count = min(color_limit, 1 << bits, max(1, useful))
    train = target[used, :3]
    options = []
    for method in (Image.Quantize.MEDIANCUT, Image.Quantize.MAXCOVERAGE, Image.Quantize.FASTOCTREE):
        q = Image.fromarray(train[None, :, :]).quantize(colors=count, method=method, dither=Image.Dither.NONE)
        colors = np.array(q.getpalette(), dtype=np.uint8).reshape(-1, 3)[:count]
        flat = target[:, :, :3].reshape(-1, 3).astype(float)
        indices = np.empty(len(flat), np.uint8)
        for start in range(0, len(flat), 1024):
            delta = flat[start:start+1024, None, :] - colors[None, :, :].astype(float)
            indices[start:start+1024] = np.square(delta).sum(2).argmin(1)
        indices = indices.reshape(target.shape[:2])
        palette = np.zeros((1 << bits, 4), np.uint8)
        palette[:len(colors), :3] = colors; palette[:, 3] = 255
        rgba = palette[indices]
        metrics = measure(source, rgba, mask)
        reconstructed = np.array(Image.fromarray(rgba).resize((source.shape[1], source.shape[0]), Image.Resampling.BILINEAR))
        biases = []
        for ys in np.array_split(np.arange(source.shape[0]), 8):
            for xs in np.array_split(np.arange(source.shape[1]), 8):
                local_mask = occupied_mask[np.ix_(ys, xs)]
                if local_mask.any():
                    a = source[np.ix_(ys, xs)][local_mask, :3].astype(float).mean(0)
                    b = reconstructed[np.ix_(ys, xs)][local_mask, :3].astype(float).mean(0)
                    biases.append(np.mean((a-b)**2))
        bias = float(np.sqrt(np.mean(biases)) / 255)
        metrics['occupied_cell_color_rmse_255'] = bias * 255
        metrics['perceptual_loss_before_color_guard'] = metrics['perceptual_loss']
        metrics['perceptual_loss'] += .8 * bias
        raw = write_gim(indices, palette, bits)
        options.append((metrics['perceptual_loss'], int(method), raw, metrics, int(len(np.unique(indices)))))
    _, method, raw, metrics, used_colors = min(options, key=lambda r: (r[0], r[1]))
    return dict(raw=raw, entry=dict(width=size[0], height=size[1], bits=bits,
        palette_entries=1 << bits, requested_useful_colors=count, used_palette_colors=used_colors,
        quantizer='UV-occupied training; method ' + str(method), serialized_bytes=len(raw),
        pixel_palette_bytes=len(raw)-208, metrics=metrics,
        source_quality_ceiling=dict(width=source.shape[1], height=source.shape[0], useful_colors=useful),
        fully_preserved=False))


def candidates(model, images, contracts, progress=print):
    usage = model_usage({2: dict(model, texture_names=model['textures'])}, dict(zip(model['textures'], images)))
    all_choices, importance, diagnostics = [], [], []
    for name, source, contract in zip(model['textures'], images, contracts):
        progress('Analyzing atlas page ' + name)
        use = usage[name]
        features = analyze(source, use['uv_mask'], use['surface_fraction'])
        mask = occupied(source, use['uv_mask'])
        scoring = dict(features, mask=mask)
        if contract['cutout']:
            rows = []
            # Explicit experimental material bake: high-quality premultiplied
            # RGBA resampling, then binary opacity for the native cutout shader.
            # Keep the original RGBA for metrics and document this approximation.
            for size in dimensions(source.shape[1], source.shape[0]):
                if size not in OBSERVED_T8_DIMENSIONS or max(size) < 32 or max(size) > 128:
                    continue
                canonical = np.array(Image.fromarray(source).resize(size, Image.Resampling.LANCZOS))
                canonical[:, :, 3] = np.where(canonical[:, :, 3] >= 128, 255, 0)
                canonical[canonical[:, :, 3] == 0] = 0
                row = encode(canonical, size, 8, 256)
                ix, pal = read_gim(row['raw'])
                row['entry']['metrics'] = measure(source, pal[ix], mask)
                row['entry']['opacity_bake'] = 'NormalFx alpha -> resampled binary PSP cutout; original fractional alpha not exact'
                row['entry']['source_quality_ceiling'] = dict(width=source.shape[1], height=source.shape[0], useful_colors=features['useful_source_colors'])
                rows.append(row)
            rejected = []
        else:
            sensitive = use['head_fraction'] > .5
            rows, rejected = [], []
            for size in dimensions(source.shape[1], source.shape[0]):
                if sensitive and min(size) < 64:
                    rejected.append(dict(size=size, reason='Whole cranial page 64-pixel axis floor')); continue
                if contract['bits'] == 8 and size not in OBSERVED_T8_DIMENSIONS:
                    continue
                limits = (16,) if contract['bits'] == 4 else (256,)
                for colors in limits:
                    rows.append(encode_occupied(source, size, contract['bits'], colors, mask))
        if not rows:
            raise ValueError('No source-bounded legal texture representation: ' + name)
        # Compress each actual GIM once for a cheap marginal search. Whole PAC
        # size is independently built/enforced before and after each upgrade.
        for row in rows:
            row['entry']['individual_bpe_bytes'] = len(compress(row['raw']))
        rows.sort(key=lambda r: (r['entry']['individual_bpe_bytes'], r['entry']['metrics']['perceptual_loss']))
        frontier = []; loss = float('inf')
        for row in rows:
            if row['entry']['metrics']['perceptual_loss'] < loss - 1e-10:
                frontier.append(row); loss = row['entry']['metrics']['perceptual_loss']
        all_choices.append(frontier); importance.append(features['importance_score'])
        diagnostics.append(dict(name=name, analysis=features, model_usage={k: v for k, v in use.items() if k != 'uv_mask'},
                                candidates=[r['entry'] for r in frontier], rejected=rejected))
    return all_choices, importance, diagnostics


def allocate(base, raw_model, model, images, contracts, output, target=IN_RING_MAX_PAC_BYTES, progress=print, candidate_factory=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    choices, importance, diagnostics = (candidate_factory or candidates)(model, images, contracts, progress)
    encoded_model = compress(raw_model)
    if decompress(encoded_model) != raw_model:
        raise ValueError('Cached model compression failed round trip')
    retained_memory = base_memory = 0
    for section, raw in sections(base):
        if len(raw) >= 16 and raw[4:16] == bytes.fromhex('000100000000000010000000'):
            table = parse_textures(raw)
            if not all(t['extension'] == 'gim' for t in table):
                continue
            memory = sum(t['size'] - 208 for t in table)
            base_memory += memory
            if section['id'] != 9:
                retained_memory += memory
    def build(selection):
        rows = [choices[j][i] for j, i in enumerate(selection)]
        table = texture_table(model['textures'], [r['raw'] for r in rows], gim_reader=read_gim)
        # Reuse exact encoded model while measuring many texture tables. Both
        # BPE and PAC rewriting are the existing unmodified implementations.
        encoded_table = compress(table)
        if decompress(encoded_table) != table:
            raise ValueError('Texture table compression failed round trip')
        pac = rewrite_sections(base, {2: encoded_model, 9: encoded_table})
        memory = retained_memory + sum(r['entry']['pixel_palette_bytes'] for r in rows)
        return pac, memory
    selected = [0] * len(choices)
    pac, memory = build(selected)
    minimum = dict(pac_bytes=len(pac), pixel_palette_bytes=memory)
    if len(pac) > target or memory > base_memory:
        (output / 'failed-minimum.json').write_text(json.dumps(dict(minimum=minimum,
            target_bytes=target, native_base_memory_envelope=base_memory, textures=diagnostics), indent=2))
        raise ValueError(f'Measured texture minimum does not fit: {len(pac)}/{target} bytes, {memory}/{base_memory} pixel/palette')
    decisions = []; rejected = set()
    # Rank upgrades using individually encoded BPE sizes; accept only after an
    # exact existing packer measurement. This is not a global optimum proof.
    for _ in range(512):
        upgrades = []
        for j, rows in enumerate(choices):
            old = rows[selected[j]]['entry']
            for i in range(selected[j] + 1, len(rows)):
                if (tuple(selected), j, i) in rejected:
                    continue
                new = rows[i]['entry']
                benefit = importance[j] * (old['metrics']['perceptual_loss'] - new['metrics']['perceptual_loss'])
                extra = new['individual_bpe_bytes'] - old['individual_bpe_bytes']
                if benefit > 1e-10:
                    upgrades.append((benefit / max(1, extra), benefit, -j, -i))
        if not upgrades:
            break
        _, gain, negative_j, negative_i = max(upgrades)
        j, i = -negative_j, -negative_i
        trial = selected.copy(); trial[j] = i
        candidate, proposed_memory = build(trial)
        if len(candidate) <= target and proposed_memory <= base_memory:
            decisions.append(dict(texture=model['textures'][j], candidate_index=i, quality_gain=gain,
                                  pac_bytes=len(candidate), pixel_palette_bytes=proposed_memory))
            selected, pac, memory = trial, candidate, proposed_memory
        else:
            rejected.add((tuple(selected), j, i))
    else:
        raise ValueError('Texture trial did not converge')
    if len(pac) > target or memory > base_memory:
        raise ValueError('Final serialized texture budget violation')
    gims = {}
    for j, (name, i) in enumerate(zip(model['textures'], selected)):
        row = choices[j][i]; gims[name] = row['raw']
        diagnostics[j]['selected'] = row['entry']
        (output / (name + '.gim')).write_bytes(row['raw'])
        ix, pal = read_gim(row['raw']); Image.fromarray(pal[ix]).save(output / (name + '.png'))
    report = dict(pac_bytes=len(pac), target_bytes=target, unused_bytes=target - len(pac),
        pixel_palette_bytes=memory, native_base_memory_envelope=base_memory,
        retained_base_pixel_palette_bytes=retained_memory, minimum=minimum, decisions=decisions,
        algorithm='Individual BPE marginal ranking; each accepted upgrade measured through unchanged complete PAC packer',
        memory_scope='Conservative observed base texture envelope; total runtime heap behavior UNKNOWN', textures=diagnostics)
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    canonical = package_models(base, raw_model, texture_table(model['textures'], list(gims.values()), gim_reader=read_gim), {})
    if canonical != pac:
        raise ValueError('Texture search differs from unchanged canonical packaging')
    return pac, gims, report
