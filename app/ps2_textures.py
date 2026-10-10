"""Decode linear PS2 RTX3 host images before the pinned PSP texture budget.

RTX3 contains upload pixels, not a GS VRAM dump. Do not apply a VRAM
unswizzle to these payloads. The original PSMT8 case uses the pinned reader.
"""
import json
import struct

import numpy as np
from PIL import Image

from stable_pipeline import texture_convert as psp
from stable_pipeline.pac_inspect import FormatError, inspect_pac
from tools.pac_inspect import FormatError as SourceFormatError
from tools.yobj_read import load_model

PSM_NAMES = {0: 'PSMCT32', 1: 'PSMCT24', 2: 'PSMCT16', 10: 'PSMCT16S',
             19: 'PSMT8', 20: 'PSMT4'}


def _alpha(values):
    return np.minimum(values.astype(np.uint16) * 255 // 128, 255).astype(np.uint8)


def _colors(raw, fmt):
    if fmt in (2, 10):
        if len(raw) % 2:
            raise FormatError('Truncated 16-bit PS2 colors')
        words = np.frombuffer(raw, dtype='<u2')
        rgba = np.empty((len(words), 4), dtype=np.uint8)
        for channel, shift in enumerate((0, 5, 10)):
            value = (words >> shift) & 31
            rgba[:, channel] = (value << 3) | (value >> 2)
        rgba[:, 3] = (words >> 15) * 255
        return rgba
    stride = 4 if fmt == 0 else 3 if fmt == 1 else 0
    if not stride or len(raw) % stride:
        raise FormatError(f'Unsupported or truncated PS2 color format {fmt}')
    colors = np.frombuffer(raw, dtype=np.uint8).reshape(-1, stride)
    rgba = np.full((len(colors), 4), 255, dtype=np.uint8)
    rgba[:, :3] = colors[:, :3]
    if fmt == 0:
        rgba[:, 3] = _alpha(colors[:, 3])
    return rgba


def read_rtx3(data):
    """Return RGBA pixels and format diagnostics; preserve source cutout alpha."""
    if len(data) < 64 or data[:4] != b'RTX3' or int.from_bytes(data[4:8], 'little') + 8 != len(data):
        raise FormatError('Invalid RTX3 header/length')
    tex0 = struct.unpack_from('<Q', data, 8)[0]
    psm, cpsm = (tex0 >> 20) & 63, (tex0 >> 51) & 15
    csm, csa = (tex0 >> 55) & 1, (tex0 >> 56) & 31
    width, height = 1 << ((tex0 >> 26) & 15), 1 << ((tex0 >> 30) & 15)
    details = {'container': 'RTX3', 'psm': psm, 'format': PSM_NAMES.get(psm, f'PSM {psm}'),
               'cpsm': cpsm, 'csm': csm, 'csa': csa, 'width': width, 'height': height}
    context = f"{details['format']}, CPSM={cpsm}, CSM={csm}, CSA={csa}, {width}x{height}"
    try:
        size, offset = struct.unpack_from('<2I', data, 36)
        start = offset + 8
        if width > 4096 or height > 4096 or start < 64 or start + size > len(data):
            raise FormatError('Invalid RTX3 image dimensions/offset')
        count = width * height
        raw, clut = data[start:start + size], data[start + size:]
        if psm in (19, 20):
            if size != (count if psm == 19 else (count + 1) // 2):
                raise FormatError('Unsupported RTX3 indexed pixel layout')
            if cpsm not in (0, 2, 10):
                raise FormatError('Unsupported RTX3 palette color format')
            palette = _colors(clut, cpsm)
            expected = 256 if psm == 19 else 16
            if len(palette) not in ({256} if psm == 19 else {16, 256}):
                raise FormatError('Unsupported RTX3 palette size')
            # The PS2 CSM1 CLUT swaps address bits 3 and 4 for a full table.
            # A compact 16-color host palette is already in index order.
            if csm == 0 and len(palette) == 256:
                i = np.arange(256)
                palette = palette[(i & ~24) | ((i & 8) << 1) | ((i & 16) >> 1)]
            if psm == 20 and len(palette) == 256:
                bank = csa * 16
                if bank + 16 > len(palette):
                    raise FormatError('RTX3 CLUT bank is outside the stored palette')
                palette = palette[bank:bank + 16]
            elif psm == 19 and csa:
                raise FormatError('Nonzero CLUT bank on PSMT8 is not supported')
            packed = np.frombuffer(raw, dtype=np.uint8)
            if psm == 20:
                indices = np.empty(len(packed) * 2, dtype=np.uint8)
                indices[::2], indices[1::2] = packed & 15, packed >> 4
                indices = indices[:count].reshape(height, width)
            else:
                indices = packed.reshape(height, width)
            # This path preserves the working sample's exact decoding.
            if (psm, cpsm, csm, csa) == (19, 0, 0, 0):
                indices, palette = psp.read_rtx3(data)
            details['palette_entries'] = expected
            return palette[indices], details
        if psm in (0, 1, 2, 10):
            if clut:
                raise FormatError('Unexpected trailing palette on direct-color RTX3')
            if psm == 1 and size == count * 4:
                # PSMCT24 can be uploaded in 32-bit words; its fourth byte is
                # padding, never alpha.
                rgba = np.frombuffer(raw, dtype=np.uint8).reshape(count, 4).copy()
                rgba[:, 3] = 255
            else:
                rgba = _colors(raw, psm)
            if len(rgba) != count:
                raise FormatError('Unsupported RTX3 direct-color pixel layout')
            return rgba.reshape(height, width, 4), details
        raise FormatError('Unsupported PS2 RTX3 pixel format')
    except FormatError as exc:
        raise FormatError(f'{exc} ({context})') from exc


def read_source(source, *, texture_names=None):
    """Decode only model-referenced textures; prefer the main costume section."""
    data = source.read_bytes()
    # The historic opacity-fix snapshot remains hash-pinned. Use the maintained
    # reader for main-section selection, preserving this module's error type.
    try:
        model = load_model(source) if texture_names is None else {'textures': list(texture_names)}
    except SourceFormatError as exc:
        raise FormatError(str(exc)) from exc
    textures = {}
    for section in inspect_pac(data)['sections']:
        for entry in section.get('textures', []):
            if entry['extension'].lower() != 'txc':
                continue
            name = entry['name'].lower()
            if name not in textures or section['id'] == 9:
                offset = section['offset'] + entry['offset']
                textures[name] = (data[offset:offset + entry['size']], section['id'])
    decoded = []
    for index, name in enumerate(model['textures']):
        if name.lower() not in textures:
            raise FormatError(f'Missing source texture {name} in {source.name}')
        raw, section = textures[name.lower()]
        try:
            rgba, details = read_rtx3(raw)
        except FormatError as exc:
            raise FormatError(f'Texture "{name}" in {source.name}, PAC section {section}: {exc}') from exc
        decoded.append((index, name, raw, rgba, details))
    return decoded


def convert_pac(source, output, *, decoded=None, max_dimension=64, bits=4):
    """Use the original budget/GIM writer after expanded PS2 source decoding."""
    if bits not in (4, 8) or max_dimension < 32 or max_dimension & (max_dimension - 1):
        raise FormatError('Texture budget must use 4/8 bits and a power-of-two cap of at least 32')
    decoded = read_source(source) if decoded is None else decoded
    converted = []
    for index, name, raw, rgba, details in decoded:
        if ((details['psm'], details['cpsm'], details['csm'], details['csa']) == (19, 0, 0, 0)
                and details['width'] >= 32 and details['height'] >= 8):
            # Reuse all original operations for the accepted source format.
            pixels, palette = psp.read_rtx3(raw)
            pixels, palette = psp.budget_texture(pixels, palette, max_dimension, bits)
        else:
            image = Image.fromarray(rgba)
            width, height = image.size
            while max(width, height) > max_dimension:
                width, height = max(32, width // 2), max(8, height // 2)
            image = image.resize((max(32, width), max(8, height)), Image.Resampling.LANCZOS)
            quantized = image.quantize(colors=1 << bits, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
            palette = np.zeros((1 << bits, 4), dtype=np.uint8)
            values = np.array(quantized.getpalette('RGBA'), dtype=np.uint8).reshape(-1, 4)
            palette[:len(values)] = values
            palette[palette[:, 3] >= 252, 3] = 255
            palette[palette[:, 3] <= 3, 3] = 0
            pixels = np.array(quantized, dtype=np.uint8)
        gim = psp.write_gim4(pixels, palette) if bits == 4 else psp.write_gim8(pixels, palette)
        back_pixels, back_palette = psp.read_gim(gim)
        if not np.array_equal(pixels, back_pixels) or not np.array_equal(palette, back_palette):
            raise FormatError(f'GIM round trip altered texture {name}')
        converted.append((index, name, pixels, palette, gim, details))
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    for index, name, pixels, palette, gim, details in converted:
        stem = f'texture_{index:02d}'
        Image.fromarray(palette[pixels]).save(output / (stem + '.png'))
        (output / (stem + '.gim')).write_bytes(gim)
        entries.append({'index': index, 'name': name, 'width': pixels.shape[1], 'height': pixels.shape[0],
                        'gim': stem + '.gim', 'png': stem + '.png', 'gim_bytes': len(gim), 'bits': bits,
                        'source_dimensions': [details['width'], details['height']], 'source_format': details})
    manifest = {'textures': entries, 'scope': 'Linear PS2 RTX3 indexed4/indexed8 and direct color; PSP GIM',
                'validation': 'Every GIM decodes to exactly the converted image indices and RGBA palette',
                'max_dimension': max_dimension, 'color_depth': bits, 'lossy_resize_or_quantization': True}
    (output / 'textures.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest
