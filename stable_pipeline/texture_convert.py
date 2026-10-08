"""Sample-specific RTX3 PSMT8 -> PNG and PSP GIM indexed8 conversion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

import numpy as np
from PIL import Image

try:
    from .pac_inspect import FormatError, inspect_pac
    from .yobj_read import load_model
except ImportError:
    from pac_inspect import FormatError, inspect_pac
    from yobj_read import load_model


def read_rtx3(data):
    if len(data) < 64 or data[:4] != b'RTX3' or int.from_bytes(data[4:8], 'little') + 8 != len(data):
        raise FormatError('Unsupported RTX3 header/length')
    tex0 = struct.unpack_from('<Q', data, 8)[0]
    if (tex0 >> 20) & 63 != 19 or (tex0 >> 51) & 15 != 0 or (tex0 >> 55) & 1 != 0:
        raise FormatError('Only observed PSMT8 / 32-bit CSM1 palettes are supported')
    width, height = 1 << ((tex0 >> 26) & 15), 1 << ((tex0 >> 30) & 15)
    size, offset = struct.unpack_from('<2I', data, 36)
    start = offset + 8
    if size != width * height or start < 64 or start + size + 1024 != len(data):
        raise FormatError('Unsupported RTX3 pixel/palette layout')
    # These RTX3 host image payloads are linear. GS VRAM swizzle is not an
    # additional transform on this file's byte array.
    indices = np.frombuffer(data[start:start + size], dtype=np.uint8).reshape(height, width).copy()
    palette = np.frombuffer(data[start + size:], dtype=np.uint8).reshape(256, 4).copy()
    i = np.arange(256)
    order = (i & ~24) | ((i & 8) << 1) | ((i & 16) >> 1)
    palette = palette[order]
    palette[:, 3] = np.minimum(palette[:, 3].astype(np.uint16) * 255 // 128, 255)
    return indices, palette


def _gim_addresses(width, height):
    if width % 16 or height % 8:
        raise FormatError('GIM swizzle requires width multiple of 16 and height multiple of 8')
    y, x = np.indices((height, width))
    return ((y // 8) * (width // 16) + x // 16) * 128 + (y % 8) * 16 + x % 16


def _block(kind, size):
    return struct.pack('<HHIII', kind, 16, size, size if kind in (4, 5) else 16, 16)


def _image_header(fmt, order, width, height, bits, size, palette=False):
    data = bytearray(64)
    struct.pack_into('<I6H', data, 0, 48, fmt, order, width, height, bits, 16)
    struct.pack_into('<2H', data, 16, 1 if palette else 8, 2)
    struct.pack_into('<3I', data, 24, 48, 64, 64 + size)
    struct.pack_into('<4H', data, 40, 2 if palette else 1, 1, 3, 1)
    struct.pack_into('<I', data, 48, 64)
    return bytes(data)


def write_gim8(indices, palette):
    height, width = indices.shape
    if palette.shape != (256, 4) or indices.dtype != np.uint8 or palette.dtype != np.uint8:
        raise FormatError('GIM8 requires uint8 pixels and a 256-entry RGBA palette')
    addresses = _gim_addresses(width, height)
    pixels = np.empty(width * height, dtype=np.uint8)
    pixels[addresses] = indices
    pixel_block = _block(4, 80 + pixels.size) + _image_header(5, 1, width, height, 8, pixels.size) + pixels.tobytes()
    palette_block = _block(5, 1104) + _image_header(3, 0, 256, 1, 32, 1024, palette=True) + palette.tobytes()
    size = 48 + len(pixel_block) + len(palette_block)
    return b'MIG.00.1PSP\0\0\0\0\0' + _block(2, size - 16) + _block(3, size - 32) + pixel_block + palette_block


def read_gim8(data):
    if len(data) < 128 or data[:12] != b'MIG.00.1PSP\0':
        raise FormatError('Missing GIM header')
    if struct.unpack_from('<I', data, 20)[0] + 16 != len(data):
        raise FormatError('GIM length mismatch')
    fmt, order, width, height, bits = struct.unpack_from('<5H', data, 68)
    if (fmt, order, bits) != (5, 1, 8):
        raise FormatError('Only swizzled indexed8 GIM is supported')
    pixel_size = width * height
    pixel_block_size = struct.unpack_from('<I', data, 52)[0]
    palette_start = 48 + pixel_block_size
    if pixel_block_size != 80 + pixel_size or palette_start + 1104 != len(data):
        raise FormatError('GIM block layout mismatch')
    palette_fmt = struct.unpack_from('<H', data, palette_start + 20)[0]
    if palette_fmt != 3:
        raise FormatError('Unsupported GIM palette format')
    raw = np.frombuffer(data[128:128 + pixel_size], dtype=np.uint8)
    indices = raw[_gim_addresses(width, height)].copy()
    palette = np.frombuffer(data[palette_start + 80:], dtype=np.uint8).reshape(256, 4).copy()
    return indices, palette


def write_gim4(indices, palette):
    height, width = indices.shape
    if width % 32 or height % 8 or indices.dtype != np.uint8 or palette.shape != (16, 4) or palette.dtype != np.uint8 or (indices > 15).any():
        raise FormatError('GIM4 requires 16-entry RGBA palette, 4-bit indices and 32x8-aligned dimensions')
    packed = indices[:, ::2] | (indices[:, 1::2] << 4)
    pixels = np.empty(packed.size, dtype=np.uint8)
    pixels[_gim_addresses(width // 2, height)] = packed
    image = _block(4, 80 + pixels.size) + _image_header(4, 1, width, height, 4, pixels.size) + pixels.tobytes()
    colors = _block(5, 144) + _image_header(3, 0, 16, 1, 32, 64, palette=True) + palette.tobytes()
    size = 48 + len(image) + len(colors)
    return b'MIG.00.1PSP\0\0\0\0\0' + _block(2, size - 16) + _block(3, size - 32) + image + colors


def read_gim4(data):
    if len(data) < 128 or data[:12] != b'MIG.00.1PSP\0' or struct.unpack_from('<I', data, 20)[0] + 16 != len(data):
        raise FormatError('Invalid GIM4 header/length')
    fmt, order, width, height, bits = struct.unpack_from('<5H', data, 68)
    if (fmt, order, bits) != (4, 1, 4) or width % 32 or height % 8:
        raise FormatError('Unsupported GIM4 image layout')
    pixel_size = width * height // 2
    palette_start = 128 + pixel_size
    if struct.unpack_from('<I', data, 52)[0] != 80 + pixel_size or palette_start + 144 != len(data) or struct.unpack_from('<H', data, palette_start + 20)[0] != 3:
        raise FormatError('Unsupported GIM4 palette/block layout')
    raw = np.frombuffer(data[128:palette_start], dtype=np.uint8)
    packed = raw[_gim_addresses(width // 2, height)]
    indices = np.empty((height, width), dtype=np.uint8)
    indices[:, ::2], indices[:, 1::2] = packed & 15, packed >> 4
    colors = np.frombuffer(data[palette_start + 80:], dtype=np.uint8).reshape(16, 4).copy()
    return indices, colors


def read_gim(data):
    if len(data) < 78:
        raise FormatError('Truncated GIM')
    bits = struct.unpack_from('<H', data, 76)[0]
    if bits == 4:
        return read_gim4(data)
    return read_gim8(data)


def budget_texture(indices, palette, max_dimension, bits):
    if bits not in (4, 8) or max_dimension < 32 or max_dimension & (max_dimension - 1):
        raise FormatError('Texture budget must use 4/8 bits and a power-of-two cap of at least 32')
    image = Image.fromarray(palette[indices])
    width, height = image.size
    while max(width, height) > max_dimension:
        width, height = max(32, width // 2), max(8, height // 2)
    if bits == 4:
        width = max(32, width)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    quantized = image.quantize(colors=1 << bits, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    colors = np.zeros((1 << bits, 4), dtype=np.uint8)
    values = np.array(quantized.getpalette('RGBA'), dtype=np.uint8).reshape(-1, 4)
    colors[:len(values)] = values
    # Quantizer averages can turn an opaque plateau into alpha 254. Keep the
    # transparent/opaque endpoints while retaining intermediate alpha values.
    colors[colors[:, 3] >= 252, 3] = 255
    colors[colors[:, 3] <= 3, 3] = 0
    return np.array(quantized, dtype=np.uint8), colors


def convert_pac(source, output, *, max_dimension=None, bits=8):
    data = source.read_bytes()
    report = inspect_pac(data)
    model = load_model(source)
    textures = {}
    for section in report['sections']:
        for entry in section.get('textures', []):
            if entry['extension'] != 'txc':
                continue
            offset = section['offset'] + entry['offset']
            name = entry['name'].lower()
            # Extra costume sections can repeat names: prefer main section 9.
            if name not in textures or section['id'] == 9:
                textures[name] = data[offset:offset + entry['size']]
    converted = []
    for index, name in enumerate(model['textures']):
        if name.lower() not in textures:
            raise FormatError(f'Missing source texture {name}')
        pixels, palette = read_rtx3(textures[name.lower()])
        original_size = list(pixels.shape[::-1])
        if max_dimension is not None:
            pixels, palette = budget_texture(pixels, palette, max_dimension, bits)
        elif bits != 8:
            raise FormatError('A texture size budget is required for color-depth conversion')
        gim = write_gim4(pixels, palette) if bits == 4 else write_gim8(pixels, palette)
        back_pixels, back_palette = read_gim(gim)
        if not np.array_equal(pixels, back_pixels) or not np.array_equal(palette, back_palette):
            raise FormatError('GIM round trip altered pixels or palette')
        converted.append((index, name, pixels, palette, gim, original_size))
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    for index, name, pixels, palette, gim, original_size in converted:
        stem = f'texture_{index:02d}'
        Image.fromarray(palette[pixels]).save(output / (stem + '.png'))
        (output / (stem + '.gim')).write_bytes(gim)
        entries.append({'index': index, 'name': name, 'width': pixels.shape[1], 'height': pixels.shape[0],
                        'gim': stem + '.gim', 'png': stem + '.png', 'gim_bytes': len(gim), 'bits': bits,
                        'source_dimensions': original_size})
    manifest = {'textures': entries, 'scope': f'Observed linear PSMT8 RTX3 only; PSP indexed{bits} GIM',
                'validation': 'Every GIM decodes to exactly the converted image indices and RGBA palette',
                'max_dimension': max_dimension, 'color_depth': bits,
                'lossy_resize_or_quantization': max_dimension is not None}
    (output / 'textures.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def write_preview_textures(manifest, textures_path, model_path):
    """Supply same-directory image names used by the YOBJ and DAE references."""
    files = []
    for entry in manifest['textures']:
        name = entry['name']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise FormatError('Texture name is unsafe for a preview filename')
        for extension in ('png', 'gim'):
            source_name = entry[extension]
            if not re.fullmatch(r'texture_[0-9]+\.' + extension, source_name):
                raise FormatError('Unexpected preview texture source filename')
            destination = model_path / (name + '.' + extension)
            with destination.open('xb') as stream:
                stream.write((textures_path / source_name).read_bytes())
            files.append(destination.name)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(convert_pac(args.source, args.output), indent=2))
    except (OSError, FormatError) as exc:
        print(f'Texture conversion failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
