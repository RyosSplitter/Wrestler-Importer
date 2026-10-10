"""Generate tiny, original synthetic vectors from the documented byte layout.

Standard library only. Deliberately imports no project reader, writer or game
asset. These zero-state templates exercise contracts, not PSP gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/hctp_psp'
POSITIONS = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (1., 1., 0.)]
WEIGHTS = [(1., 0.), (.25, .75), (.5, .5), (0., 1.)]


def bones():
    result = bytearray(160)
    for i, name in enumerate((b'root', b'child')):
        a = 80*i
        result[a:a+len(name)] = name
        struct.pack_into('<4f', result, a+16, 0, i, 0, 1)
        struct.pack_into('<i', result, a+48, i-1)
        struct.pack_into('<3f', result, a+64, 0, i, 0)
    return result


class Layout:
    def __init__(self):
        self.raw = bytearray(72)
        self.raw[:4] = b'YOBJ'
        self.locations = []

    def alloc(self, raw):
        self.raw += bytes((-(len(self.raw)-8)) % 16)
        address = len(self.raw)
        self.raw += raw
        return address

    def u32(self, address, value):
        struct.pack_into('<I', self.raw, address, value)

    def ptr(self, address, target):
        self.u32(address, target-8)
        self.locations.append(address)

    def finish(self):
        end = len(self.raw)
        self.u32(4, end-8)
        self.u32(12, end-8)
        # Independent implementation of documented sorted delta encoding.
        payload = bytearray()
        previous = 8
        for address in sorted(self.locations):
            delta = (address-previous)//4
            if delta <= 63:
                payload += bytes([0x40 | delta])
            elif delta <= 16383:
                payload += (0x8000 | delta).to_bytes(2, 'big')
            else:
                payload += (0xc0000000 | delta).to_bytes(4, 'big')
            previous = address
        payload += bytes((-(end+8+len(payload))) % 16)
        self.raw += b'POF0' + struct.pack('<I', len(payload)) + payload
        return bytes(self.raw)


def model(psp):
    f = Layout()
    mesh = f.alloc(bytes(64))
    f.u32(24, 1); f.u32(28, 2); f.u32(32, 1)
    f.ptr(36, mesh)
    if psp:
        palette = f.alloc(struct.pack('<6I', 4, 2, 0, 0, 1, 2))
        cell = f.alloc(bytes(4))
        vertices = bytearray()
        for p, w in zip(POSITIONS, WEIGHTS):
            vertices += struct.pack('<4f4B6f', *w, p[0], p[1],
                                    255, 255, 255, 255, 0, 0, 1, *p)
        vp = f.alloc(vertices)
        material = f.alloc(bytes(144))
        strip = f.alloc(struct.pack('<4I', 3, 0, 4, 0))
        indices = f.alloc(struct.pack('<4H', 0, 1, 2, 3))
        f.u32(mesh+4, 1); f.ptr(mesh+8, palette); f.ptr(mesh+12, material)
        f.ptr(mesh+24, cell); f.u32(mesh+28, 0x57ff); f.u32(mesh+40, 4)
        struct.pack_into('<4f', f.raw, mesh+48, .5, .5, 0, 2)
        f.ptr(palette+8, vp); f.ptr(cell, vp)
        f.u32(material+24, 5); f.u32(material+132, 1)
        f.ptr(material+136, strip); f.ptr(material+140, indices)
        f.ptr(strip+12, indices)
    else:
        group = f.alloc(struct.pack('<8I', 4, 2, 0, 0, 1, 2, 0, 0))
        pos = f.alloc(b''.join(struct.pack('<4f', *p, 1) for p in POSITIONS))
        normal = f.alloc(struct.pack('<4f', 0, 0, 1, 0)*4)
        material = f.alloc(bytes(208))
        strip = f.alloc(struct.pack('<4I', 3, 3, 4, 0))
        corners = f.alloc(b''.join(struct.pack('<3fI4f', p[0], p[1], 1,
                                               i, 1, 1, 1, 1)
                                  for i, p in enumerate(POSITIONS)))
        packet = struct.pack('<4I', 0, 0, 0, 0x6c040280)
        packet += b''.join(struct.pack('<4f', *w, 0, 0) for w in WEIGHTS)
        weights = f.alloc(packet)
        f.u32(mesh, 1); f.u32(mesh+4, 1); f.ptr(mesh+8, group)
        f.ptr(mesh+12, material); f.ptr(mesh+28, weights)
        f.u32(mesh+32, 10); f.u32(mesh+36, 5); f.u32(mesh+40, 4)
        f.ptr(group+8, pos); f.ptr(group+12, normal)
        f.u32(material+196, 1); f.ptr(material+200, strip)
        f.ptr(strip+12, corners)
    f.ptr(40, f.alloc(bones()))
    f.ptr(44, f.alloc(b'skin'.ljust(16, b'\0')))
    descriptor = bytearray(32); descriptor[:9] = b'synthetic'
    struct.pack_into('<I', descriptor, 24, 1)
    f.ptr(48, f.alloc(descriptor))
    return f.finish()


def bpe_literal(raw):
    # Skip 128, explicitly store identity entry 128, skip final 127.
    payload = b'\xff\x80\xfe' + struct.pack('<H', len(raw)) + raw
    return b'BPE ' + struct.pack('<3I', 0x100, len(payload), len(raw)) + payload


def bpe_pair():
    # Full dictionaries independent of the compressor: entry250 = 'A'+'B'.
    dictionary = b'\x7f' + bytes(range(128)) + b'\x7f'
    dictionary += bytes(range(128, 250)) + b'AB' + bytes(range(251, 256))
    payload = dictionary + struct.pack('<H', 3) + bytes([250, 250, 33])
    return b'BPE ' + struct.pack('<3I', 0x100, len(payload), 5) + payload


def rtx4():
    f = bytearray(64); f[:4] = b'RTX3'
    struct.pack_into('<I', f, 4, 56+128+64)
    struct.pack_into('<Q', f, 8, (20<<20) | (5<<26) | (3<<30))
    struct.pack_into('<2I', f, 36, 128, 56)
    colors = b''.join(bytes([16*i, 0, 0, 0 if i==0 else 64 if i==1 else 128])
                      for i in range(16))
    return bytes(f) + bytes([0x10, 0xf8])*64 + colors


def gim4():
    # Independent layout vector: horizontal 0..15 ramp repeated in each row.
    width, height = 32, 8
    linear = bytes((x%16) | (((x+1)%16)<<4) for y in range(height)
                   for x in range(0, width, 2))
    def block(kind, size):
        return struct.pack('<HHIII', kind, 16, size, size if kind in (4,5) else 16, 16)
    def info(fmt, order, w, h, bits, size, palette):
        b = bytearray(64)
        struct.pack_into('<I6H', b, 0, 48, fmt, order, w, h, bits, 16)
        struct.pack_into('<2H', b, 16, 1 if palette else 8, 2)
        struct.pack_into('<3I', b, 24, 48, 64, 64+size)
        struct.pack_into('<4H', b, 40, 2 if palette else 1, 1, 3, 1)
        struct.pack_into('<I', b, 48, 64)
        return bytes(b)
    pixels = bytearray(128)
    for y in range(height):
        for x in range(width//2):
            dest = ((y//8)*((width//2)//16)+x//16)*128+(y%8)*16+x%16
            pixels[dest] = linear[y*(width//2)+x]
    colors = b''.join(bytes([16*i, 0, 0, 0 if i==0 else 127 if i==1 else 255])
                      for i in range(16))
    image = block(4, 208) + info(4,1,width,height,4,128,False) + pixels
    palette = block(5,144) + info(3,0,16,1,32,64,True) + colors
    return b'MIG.00.1PSP\0\0\0\0\0' + block(2,384) + block(3,368) + image + palette


def pac(rows):
    p = 8+8*len(rows)
    table = bytearray(b'PAC ' + struct.pack('<I', len(rows)))
    payload = bytearray()
    for sid, data in rows:
        payload += bytes((-(p+len(payload))) % 16)
        table += sid.to_bytes(2,'little') + len(payload).to_bytes(3,'little') + len(data).to_bytes(3,'little')
        payload += data
    out = table + payload
    out += bytes((-len(out)) % 2048)
    return bytes(out)


def vectors():
    hctp, psp = model(False), model(True)
    texture = gim4()
    table = struct.pack('<4I',1,0x100,0,16) + b'skin'.ljust(16,b'\0')
    table += b'gim\0' + struct.pack('<3I',len(texture),48,0) + texture
    vif = struct.pack('<4I',0,0,0,0x6c020282) + struct.pack('<8f',.25,.75,0,0,.5,.5,0,0)
    files = {'hctp-quad.yobj':hctp, 'psp-quad.yobj':psp,
             'literal.bpe':bpe_literal(b'ABAB!'), 'pair.bpe':bpe_pair(),
             'weights-offset.vif':vif, 'skin-t4.rtx3':rtx4(), 'skin-t4.gim':texture,
             'psp-quad.pac':pac([(2,bpe_literal(psp)),(9,table),(50,b'opaque-preserve')])}
    expected = {'status':'CONFIRMED synthetic contract; no game art or engine certification',
                'positions':POSITIONS,'weights':WEIGHTS,'triangles':[[0,1,2],[1,3,2]],
                'mesh_count':1,'vertex_count':4,'triangle_count':2,'bone_count':2,
                'palette_stored':[1,2],'psp_stride':44,'psp_flag':0x57ff,
                'bpe_output_hex':b'ABAB!'.hex(),'vif_first_vertex':2,
                'rtx_first_red':[0,16,128,240],'rtx_first_alpha':[0,127,255,255],
                'gim_dimensions':[32,8], 'pof0_vector':{'addresses':[12,268,65804],
                    'encoded_hex':'418040c0004000'},
                'files':{name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                         for name,raw in sorted(files.items())}}
    files['expected.json'] = (json.dumps(expected,indent=2)+'\n').encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Compare without rewriting fixtures')
    args = parser.parse_args()
    for name, raw in vectors().items():
        path = ROOT/name
        if args.check:
            if not path.exists() or path.read_bytes()!=raw:
                raise SystemExit('Fixture mismatch: '+str(path))
        else:
            ROOT.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
    print('Verified' if args.check else 'Generated', len(vectors()), 'synthetic fixture files')


if __name__=='__main__':
    main()
