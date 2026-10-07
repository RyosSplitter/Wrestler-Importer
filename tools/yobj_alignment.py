"""Pad the observed final YOBJ relocation chunk without changing relocation data."""
import struct


def align_yobj_pof0(data):
    if len(data) < 16 or data[:4] != b'YOBJ':
        raise ValueError('Missing YOBJ header for relocation alignment')
    start = struct.unpack_from('<I', data, 4)[0] + 8
    if start + 8 > len(data) or data[start:start + 4] != b'POF0':
        raise ValueError('Expected a final POF0 relocation chunk')
    size = struct.unpack_from('<I', data, start + 4)[0]
    if start + 8 + size != len(data) or start % 4:
        raise ValueError('Unsupported YOBJ relocation chunk bounds/alignment')
    # Zero terminators/padding are present in the original PSP relocation data.
    # Include new padding in the chunk length, rather than leaving stray bytes.
    padding = (-len(data)) % 16
    if not padding:
        return data
    aligned = bytearray(data)
    struct.pack_into('<I', aligned, start + 4, size + padding)
    return bytes(aligned) + bytes(padding)
