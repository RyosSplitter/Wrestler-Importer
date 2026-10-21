"""Synthetic Wii TPL/archive fixtures; no game-derived binary assets."""
import struct
import unittest

import numpy as np

from tools.wwe13_wii_inspect import decode_tpl, decode_palette, read_pach, read_model_header, rgb565
from tools.yukes_bpe import compress


def tpl(fmt,width,height,pixels,palette=None):
    h=bytearray(64 if palette is None else 96)
    struct.pack_into('>5I',h,0,0x20af30,1,12,20,0 if palette is None else 56)
    struct.pack_into('>2H2I',h,20,height,width,fmt,len(h))
    if palette is not None:
        struct.pack_into('>H',h,56,len(palette)//2)
        struct.pack_into('>2I',h,60,2,len(h)+len(pixels))
    return bytes(h)+pixels+(palette or b'')


class WiiResearchTests(unittest.TestCase):
    def test_cmpr_four_subblocks_and_big_endian_selectors(self):
        blocks=[]
        for a,b in [(0xf800,0x07e0),(0x07e0,0x001f),(0x001f,0),(0xffff,0)]:
            blocks.append(struct.pack('>2I',(a<<16)|b,0x1b1b1b1b))
        image,info=decode_tpl(tpl(14,8,8,b''.join(blocks)))
        self.assertEqual(info['format'],'CMPR')
        np.testing.assert_array_equal(image[0,0],[255,0,0,255])
        np.testing.assert_array_equal(image[0,1],[0,255,0,255])
        np.testing.assert_array_equal(image[0,4],[0,255,0,255])
        np.testing.assert_array_equal(image[4,0],[0,0,255,255])
        np.testing.assert_array_equal(image[4,4],[255]*4)

    def test_cmpr_transparency_mode(self):
        block=struct.pack('>2H4B',0,0xffff,255,255,255,255)
        image,_=decode_tpl(tpl(14,8,8,block*4))
        self.assertTrue(np.all(image[:,:,3]==0))

    def test_native_channel_expansion_uses_bit_replication(self):
        self.assertEqual(rgb565((4<<11)|(16<<5)|4),[33,65,33,255])
        values=decode_palette(struct.pack('>2H',0x8000|(4<<10)|(4<<5)|4,0x2123),2,2)
        np.testing.assert_array_equal(values[0],[33,33,33,255])
        np.testing.assert_array_equal(values[1],[17,34,51,73])

    def test_c4_high_nibble_first_and_rgb5a3_alpha(self):
        palette=struct.pack('>2H',0xfc00,0x0123)
        image,info=decode_tpl(tpl(8,8,8,bytes([0x01])*32,palette))
        np.testing.assert_array_equal(image[0,0],[255,0,0,255])
        np.testing.assert_array_equal(image[0,1],[17,34,51,0])
        self.assertEqual(info['palette_entries'],2)

    def test_c8_block_order_and_cropped_edges(self):
        palette=struct.pack('>2H',0xfc00,0x801f)
        image,_=decode_tpl(tpl(9,9,4,bytes(32)+bytes([1])*32,palette))
        self.assertEqual(image.shape,(4,9,4))
        np.testing.assert_array_equal(image[0,7],[255,0,0,255])
        np.testing.assert_array_equal(image[0,8],[0,0,255,255])

    def test_index_outside_palette_rejected(self):
        with self.assertRaises(ValueError):decode_tpl(tpl(8,8,8,bytes([0x02])*32,struct.pack('>H',0xffff)))

    def test_bad_image_offset_and_unsupported_format_rejected(self):
        data=bytearray(tpl(14,8,8,bytes(32)));struct.pack_into('>I',data,28,1000)
        with self.assertRaises(ValueError):decode_tpl(bytes(data))
        with self.assertRaises(ValueError):decode_tpl(tpl(6,8,8,bytes(256)))

    def test_bpe_pach_extracts_exact_section_bytes(self):
        payload=b'fixture decoded section';encoded=compress(payload)
        data=b'PACH'+struct.pack('<I3I',1,2,0,len(encoded))+encoded
        result=read_pach(data,0)
        self.assertEqual(result['sections'][0]['raw'],payload)
        self.assertEqual(result['sections'][0]['id'],2)

    def test_pach_outside_input_and_overlap_rejected(self):
        with self.assertRaises(ValueError):read_pach(b'PACH'+struct.pack('<I3I',1,2,4096,16),0)
        encoded=compress(b'fixture')
        data=b'PACH'+struct.pack('<I',2)+struct.pack('<3I',2,0,len(encoded))+struct.pack('<3I',9,0,len(encoded))+encoded
        with self.assertRaises(ValueError):read_pach(data,0)

    def test_other_model_layout_is_not_misidentified(self):
        with self.assertRaises(ValueError):read_model_header(b'YOBJ'+bytes(256))


if __name__=='__main__':unittest.main()
