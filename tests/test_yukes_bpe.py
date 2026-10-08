import random
import struct
import unittest

from tools.yukes_bpe import compress, decompress


class YukesBpeTests(unittest.TestCase):
    def test_hand_written_literal_block(self):
        # Skip 128 identities, emit symbol 128 as itself, skip the remaining
        # 127 identities, then a u16 little-endian count and literal tokens.
        stream = bytes([255, 128, 254])+b'\x03\x00ABC'
        wrapped = b'BPE '+struct.pack('<3I', 0x100, len(stream), 3)+stream
        self.assertEqual(decompress(wrapped), b'ABC')

    def test_round_trip_binary_and_repeated_model_attributes(self):
        rng = random.Random(71)
        values = [b'', b'\0'*20000, bytes(range(256))*20,
                  rng.randbytes(10003), (struct.pack('<8f', 0, 1, .25, .75, 3, -3, 0, 0)+b'\xff'*4)*503]
        for original in values:
            with self.subTest(length=len(original)):
                packed = compress(original)
                self.assertEqual(decompress(packed), original)
                self.assertEqual(struct.unpack_from('<I', packed, 8)[0], len(packed)-16)
        self.assertLess(len(compress(values[-1])), len(values[-1])//2)

    def test_corrupt_lengths_and_output_limits_rejected(self):
        packed = compress(b'ABCD'*2000)
        for broken in [packed[:-1], packed+b'\0', b'XXXX'+packed[4:]]:
            with self.assertRaises(ValueError):
                decompress(broken)
        with self.assertRaises(ValueError):
            decompress(packed, max_output=7999)
        broken = bytearray(packed)
        struct.pack_into('<I', broken, 12, 3)
        with self.assertRaises(ValueError):
            decompress(broken)

    def test_cyclic_dictionary_rejected(self):
        # Entry 0 expands to entry 1, which in turn expands to entry 0.
        dictionary = bytes([1, 1, 2, 0, 2, 255, 130, 252])
        stream = dictionary+b'\x01\x00\x00'
        wrapped = b'BPE '+struct.pack('<3I', 0x100, len(stream), 10)+stream
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            decompress(wrapped)


if __name__ == '__main__':
    unittest.main()
