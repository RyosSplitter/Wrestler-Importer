"""Bounded Gage byte-pair codec for the observed PSP Yukes BPE wrapper.

Each block has a 256-entry replacement dictionary and a u16 token count.
Compression is lossless; it does not reduce the expanded asset memory size.
"""
from collections import Counter
import struct


def decompress(data, max_output=32*1024*1024):
    if len(data) < 16 or data[:4] != b'BPE ':
        raise ValueError('Missing BPE wrapper')
    version, packed, unpacked = struct.unpack_from('<3I', data, 4)
    if version != 0x100 or packed+16 != len(data) or unpacked > max_output:
        raise ValueError('Unsupported BPE header/length')
    cursor, output = 16, bytearray()

    def byte():
        nonlocal cursor
        if cursor >= len(data):
            raise ValueError('Truncated BPE stream')
        value = data[cursor]
        cursor += 1
        return value

    while cursor < len(data):
        left, right, index = list(range(256)), [0]*256, 0
        while index < 256:
            count = byte()
            if count > 127:
                index += count-127
                count = 0
            if index > 256:
                raise ValueError('BPE dictionary skip out of range')
            if index == 256:
                break
            for _ in range(count+1):
                if index >= 256:
                    raise ValueError('BPE dictionary run out of range')
                left[index] = byte()
                if left[index] != index:
                    right[index] = byte()
                index += 1
        # Expand each symbol once, detecting cycles and bounding dictionary
        # expansion before allocating a large intermediate value.
        expanded, active = {}, set()

        def expand(symbol):
            if symbol in expanded:
                return expanded[symbol]
            if left[symbol] == symbol:
                result = bytes([symbol])
            else:
                if symbol in active:
                    raise ValueError('Cyclic BPE dictionary')
                active.add(symbol)
                a, b = expand(left[symbol]), expand(right[symbol])
                if len(a)+len(b) > unpacked-len(output):
                    raise ValueError('BPE dictionary exceeds declared output')
                result = a+b
                active.remove(symbol)
            expanded[symbol] = result
            return result

        for symbol in range(256):
            expand(symbol)
        length = byte() | byte()<<8
        if not length or cursor+length > len(data):
            raise ValueError('Invalid BPE block length')
        tokens = data[cursor:cursor+length]
        cursor += length
        for symbol in tokens:
            value = expanded[symbol]
            if len(output)+len(value) > unpacked:
                raise ValueError('BPE output exceeds declared size')
            output.extend(value)
    if len(output) != unpacked:
        raise ValueError('BPE output size mismatch')
    return bytes(output)


def _dictionary(left, right):
    result, index = bytearray(), 0
    while index < 256:
        if left[index] == index:
            count = 0
            while index+count < 256 and count < 128 and left[index+count] == index+count:
                count += 1
            result.append(127+count)
            index += count
            if index == 256:
                break
            # A skip byte also introduces the next single dictionary entry.
            result.append(left[index])
            if left[index] != index:
                result.append(right[index])
            index += 1
        else:
            start = index
            while index < 256 and index-start < 128 and left[index] != index:
                index += 1
            result.append(index-start-1)
            for symbol in range(start, index):
                result.extend((left[symbol], right[symbol]))
    return result


def compress(data, block_size=4000, max_distinct=200):
    if not 1 <= block_size <= 65535 or not 1 <= max_distinct <= 256 or len(data) > 32*1024*1024:
        raise ValueError('Unsupported BPE input/block size')
    payload = bytearray()
    offset = 0
    while offset < len(data):
        end, symbols = offset, set()
        while end < len(data) and end-offset < block_size:
            symbols.add(data[end])
            end += 1
            if len(symbols) >= max_distinct:
                break
        tokens = bytes(data[offset:end])
        offset = end
        left, right = list(range(256)), [0]*256
        free = [symbol for symbol in range(255, -1, -1) if symbol not in symbols]
        for symbol in free:
            pairs = Counter(zip(tokens, tokens[1:]))
            if not pairs:
                break
            pair, count = max(pairs.items(), key=lambda item: (item[1], item[0]))
            if count < 3:
                break
            replacement = tokens.replace(bytes(pair), bytes([symbol]))
            if len(tokens)-len(replacement) < 3:
                break
            left[symbol], right[symbol] = pair
            tokens = replacement
        payload.extend(_dictionary(left, right))
        payload.extend(struct.pack('<H', len(tokens)))
        payload.extend(tokens)
    result = b'BPE '+struct.pack('<3I', 0x100, len(payload), len(data))+payload
    if decompress(result) != data:
        raise ValueError('BPE compression round trip failed')
    return result
