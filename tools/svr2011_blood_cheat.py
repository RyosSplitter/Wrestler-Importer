"""Generate a guarded, captured-layout CWCheat from a PPSSPP 1.20.4 state.

No ISO, PAC, save state or production converter is modified. RAM/VRAM dumps
stay local. The output is experimental and needs a PPSSPP gameplay test.
"""
from dataclasses import dataclass
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import struct


USER_BASE = 0x08800000
GP = 0x08CF4F30
ACTOR_TABLE = 0x08D0F7AC
# Independently decoded instructions in both supplied ULUS10543 states.
FINGERPRINT = {0x08C3EDC4: 0xA21207C1, 0x08C3EDC8: 0xA21207BA,
               0x08BF3F64: 0xA26207BA, 0x08BF4034: 0x24060040}


@dataclass
class Memory:
    ram: bytes
    vram: bytes

    def buffer(self, address, size):
        if size < 0:
            raise ValueError('Negative memory range')
        if 0x08000000 <= address < 0x08000000 + len(self.ram):
            data, offset = self.ram, address-0x08000000
        elif 0x04000000 <= address < 0x04000000 + len(self.vram):
            data, offset = self.vram, address-0x04000000
        else:
            raise ValueError('Unsupported memory address: '+hex(address))
        if offset+size > len(data):
            raise ValueError('Memory span crosses an allocation boundary')
        return data, offset

    def read(self, address, size):
        data, offset = self.buffer(address, size)
        return bytes(data[offset:offset+size])

    def u32(self, address):
        return struct.unpack('<I',self.read(address,4))[0]

    def u16(self, address):
        return struct.unpack('<H',self.read(address,2))[0]

    def write(self, address, data):
        buffer, offset = self.buffer(address,len(data))
        if not isinstance(buffer,bytearray):
            raise ValueError('Snapshot is read-only; clone it for replay')
        buffer[offset:offset+len(data)] = data

    def clone(self):
        return Memory(bytearray(self.ram),bytearray(self.vram))


def decompress_zstd(payload, size):
    try:
        import zstandard
    except ImportError:
        name = ctypes.util.find_library('zstd')
        if not name:
            raise RuntimeError('Install zstandard for this analysis tool: python -m pip install zstandard')
        library = ctypes.CDLL(name)
        library.ZSTD_decompress.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
        library.ZSTD_decompress.restype = ctypes.c_size_t
        library.ZSTD_isError.argtypes = [ctypes.c_size_t]
        library.ZSTD_isError.restype = ctypes.c_uint
        source, target = ctypes.create_string_buffer(payload),ctypes.create_string_buffer(size)
        result = library.ZSTD_decompress(target,size,source,len(payload))
        if library.ZSTD_isError(result) or result != size:
            raise ValueError('Zstandard checksum, bounds or decoded length failed')
        return target.raw
    if zstandard.frame_content_size(payload)!=size:
        raise ValueError('Zstandard frame length differs from the bounded state header')
    raw = zstandard.ZstdDecompressor().decompress(payload,max_output_size=size)
    if len(raw) != size:
        raise ValueError('Decoded state length mismatch')
    return raw


def parse_state(data):
    if len(data)<176:
        raise ValueError('Truncated PPSSPP state')
    revision, compression, stored, expanded = struct.unpack_from('<4I',data)
    if revision != 5 or compression not in (0,2) or stored != len(data)-176 or not 0<expanded<=128*1024*1024:
        raise ValueError('Unsupported or invalid state header')
    version = data[16:48].split(b'\0')[0].decode('ascii')
    if version != 'v1.20.4':
        raise ValueError('Initial analysis profile supports PPSSPP v1.20.4 only')
    raw = data[176:] if compression==0 else decompress_zstd(data[176:],expanded)
    if len(raw)!=expanded:
        raise ValueError('Expanded state length mismatch')
    marker = b'Memory'.ljust(16,b'\0')
    offset = raw.find(marker,0,512)
    if offset<0 or struct.unpack_from('<I',raw,offset+16)[0]!=3:
        raise ValueError('Missing supported Memory section')
    _, cookie, size = struct.unpack_from('<3I',raw,offset+20)
    start = offset+32; end = start+size
    if cookie!=0x42 or size!=0x2000000 or end+4+0x200000+4>len(raw):
        raise ValueError('Unexpected PSP RAM size or truncated memory section')
    if raw[end:end+4]!=b'B\0\0\0' or raw[end+4+0x200000:end+8+0x200000]!=b'B\0\0\0':
        raise ValueError('RAM/VRAM boundary marker failed')
    return Memory(raw[start:end],raw[end+4:end+4+0x200000]),dict(
        version=version,state_sha256=hashlib.sha256(data).hexdigest(),
        ram_bytes=size,vram_bytes=0x200000,source_modified=False)


def layout(memory, player):
    if player not in (1,2):
        raise ValueError('First trial supports Player 1 or Player 2')
    for address, word in FINGERPRINT.items():
        if memory.u32(address)!=word:
            raise ValueError('Game code fingerprint differs: '+hex(address))
    slot = player-1
    actor = memory.u32(ACTOR_TABLE+slot*4)
    vtable = memory.u32(actor)
    if memory.u32(actor+0x484)!=slot:
        raise ValueError('Player table and actor slot disagree')
    manager = memory.u32(GP-0x2D60)
    array = memory.u32(manager)
    cache = array+slot*0x220
    model_id = memory.u32(actor+0x50)
    if model_id!=memory.u32(cache+0x18):
        raise ValueError('Actor and cached blood model identities differ')
    container = memory.u32(cache+4)
    index = memory.u32(cache+0x6C)
    if index==0xFFFFFFFF or index>=memory.u32(container+8):
        raise ValueError('This model has no cached face blood texture')
    entry = memory.u32(container+4)+index*8
    handle = memory.u32(entry)
    texture_manager = memory.u32(GP-0x2F68)
    nodes = memory.u32(texture_manager+8)
    limit = memory.u32(texture_manager+0x10)
    node = nodes+(handle&0xFFFF)*8
    if node+8>limit or memory.u32(node)!=handle:
        raise ValueError('Invalid or stale native texture handle')
    texture = memory.u32(node+4)
    if memory.read(texture+0x10,16).split(b'\0')[0]!=b'blood':
        raise ValueError('Cached face texture does not identify itself as blood')
    reader_cell = memory.u32(texture+0x58)+memory.u32(texture+0x60)*4
    reader = memory.u32(reader_cell)
    header_cell = reader+0x10
    header = memory.u32(header_cell)
    if not (memory.u16(header+4)==3 and memory.u16(header+8)==16
            and memory.u16(header+10)==1 and memory.u16(header+12)==32
            and memory.u16(header+0x2A)==1 and memory.u16(header+0x2E)==1):
        raise ValueError('Unimplemented native blood palette layout')
    palette = memory.u32(header+memory.u32(header+0x18))
    if palette!=header+0x40:
        raise ValueError('Unimplemented palette-pointer offset')
    memory.read(palette,64)
    source = cache+0x80
    rgba = memory.read(source,64)
    if max(rgba[3::4])==0:
        raise ValueError('Cached first-blood stage has no visible alpha')
    return dict(player=player,slot=slot,actor=actor,vtable=vtable,manager=manager,
        array=array,cache=cache,model_id=model_id,texture=texture,reader=reader,
        header_cell=header_cell,header=header,palette=palette,source_palette=source,
        blood_level_address=actor+0x7BA,bleeding_flag_address=actor+0x7C1)


def offset(address):
    result = address-USER_BASE
    if not 0<=result<0x01800000:
        raise ValueError('CWCheat address must be in PSP user RAM')
    return result


def generate(memory, binding):
    guards = [(a,w) for a,w in FINGERPRINT.items()]
    guards += [(ACTOR_TABLE+4*binding['slot'],binding['actor']),
               (binding['actor'],binding['vtable']),
               (binding['actor']+0x484,binding['slot']),
               (binding['actor']+0x50,binding['model_id']),
               (GP-0x2D60,binding['manager']),
               (binding['manager'],binding['array']),
               (binding['cache']+0x18,binding['model_id']),
               (binding['texture']+0x58,memory.u32(binding['texture']+0x58)),
               (binding['texture']+0x60,memory.u32(binding['texture']+0x60)),
               (binding['header_cell'],binding['header'])]
    lines = [(0xC0000000|offset(a),w) for a,w in guards]
    # Type-5 copies are relative to USER_BASE and cannot address this VRAM
    # destination. PPSSPP's type-6 copy uses the absolute pointer read from RAM.
    # source = *header_cell + delta; destination = *header_cell + 0x40.
    delta = (binding['source_palette']-binding['header'])&0xFFFFFFFF
    lines += [(0x60000000|offset(binding['header_cell']),64),
              (0x00000002,delta),(0x10000040,0),
              (offset(binding['blood_level_address']),1),
              (offset(binding['bleeding_flag_address']),1)]
    return lines


def replay(memory, lines):
    """Bounded interpreter of only the PPSSPP CWCheat subset emitted above."""
    result = memory.clone(); writes = []; i = 0
    while i<len(lines):
        a,b = lines[i];i+=1; kind=a>>28; address=((a&0x0FFFFFFF)+USER_BASE)&0x3FFFFFFF
        if kind==0xC:
            if result.u32(address)!=b:
                return result,dict(status='guard stopped',writes=writes)
        elif kind==0x6:
            if i+2>len(lines):raise ValueError('Truncated pointer copy')
            spec,delta=lines[i];copy,_=lines[i+1];i+=2
            if spec!=2 or copy!=0x10000040 or b!=64:
                raise ValueError('Unexpected pointer-copy variant')
            base=result.u32(address);source=(base+delta)&0xFFFFFFFF;destination=base+0x40
            result.write(destination,result.read(source,64));writes.append(dict(address=destination,bytes=64))
        elif kind==0 and b<=255:
            result.write(address,bytes([b]));writes.append(dict(address=address,bytes=1))
        else:raise ValueError('Unexpected generated CWCheat operation')
    return result,dict(status='offline replay passed',writes=writes)


def validate_activation(memory, binding, lines):
    """Check an activation against native first-stage semantics without an after state."""
    for key in ('blood_level_address', 'bleeding_flag_address'):
        if memory.read(binding[key], 1) != b'\0':
            raise ValueError('Snapshot is not before the first-blood transition')
    if memory.read(binding['palette'], 64) != bytes(64):
        raise ValueError('Snapshot live blood palette is already visible or unsupported')
    changed, check = replay(memory, lines)
    expected = [(binding['palette'], 64), (binding['blood_level_address'], 1),
                (binding['bleeding_flag_address'], 1)]
    if check['status'] != 'offline replay passed' or check['writes'] != [
            dict(address=address, bytes=size) for address, size in expected]:
        raise ValueError('Activation did not perform exactly the declared blood writes')
    if changed.read(binding['palette'], 64) != memory.read(binding['source_palette'], 64):
        raise ValueError('Activation failed to copy the native first-stage palette')
    for key in ('blood_level_address', 'bleeding_flag_address'):
        if changed.read(binding[key], 1) != b'\1':
            raise ValueError('Activation failed to set the native blood records')
    restored = changed.clone()
    for address, size in expected:
        restored.write(address, memory.read(address, size))
    if restored.ram != memory.ram or restored.vram != memory.vram:
        raise ValueError('Activation changed unrelated memory')
    repeated, _ = replay(changed, lines)
    if repeated.ram != changed.ram or repeated.vram != changed.vram:
        raise ValueError('Activation was not idempotent')
    return changed, check


def run_snapshot(before_path, output, player):
    """Generate a new guarded layout using the previously validated native profile.

    There is deliberately no claim of an observed after-state comparison here.
    """
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    before_bytes = Path(before_path).read_bytes()
    memory, metadata = parse_state(before_bytes)
    binding = layout(memory, player)
    lines = generate(memory, binding)
    _, check = validate_activation(memory, binding, lines)
    text = '_S ULUS-10543\n_G WWE SmackDown vs. RAW 2011 [US]\n'
    text += '_C0 Instant Blood P%d - Snapshot Layout TEST\n' % player
    text += ''.join('_L 0x%08X 0x%08X\n' % line for line in lines)
    report = dict(
        status='EXPERIMENTAL: single-state offline activation verified; this layout awaits gameplay testing',
        before=metadata, after=None, observed_after_state_comparison=False,
        binding={k: hex(v) if k not in ('player', 'slot') else v for k, v in binding.items()},
        native_profile='ULUS10543 first-blood profile established from the original before/after pair; user reports that code worked in its captured match',
        pre_blood_palette_all_transparent=True,
        cached_first_stage_palette_sha256=hashlib.sha256(memory.read(binding['source_palette'], 64)).hexdigest(),
        replay=check, only_target_blood_records_changed=True, idempotence_verified=True,
        other_player_unchanged=True, game_code_pac_and_save_states_modified=False,
        guard_count=len(lines)-5,
        limitations=['Only this captured allocation layout; guards stop it if allocations change.',
                     'Disable after activation; leaving enabled holds the first blood stage.',
                     'Copies native cached palette and sets flags; does not reproduce every callback or statistic.',
                     'No observed after state or live test for this new layout yet.'])
    if Path(before_path).read_bytes() != before_bytes:
        raise ValueError('Source snapshot changed during analysis')
    output.mkdir(parents=True)
    (output/'ULUS10543-Instant-Blood-TEST.ini').write_text(text)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def run(before_path, after_path, output, player):
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    before_bytes=Path(before_path).read_bytes();after_bytes=Path(after_path).read_bytes()
    a,am=parse_state(before_bytes);b,bm=parse_state(after_bytes)
    x,y=layout(a,player),layout(b,player)
    if x!=y:raise ValueError('Before/after allocation layout differs; cannot use a frozen-layout trial')
    for key in ('blood_level_address','bleeding_flag_address'):
        if a.read(x[key],1)!=b'\0' or b.read(x[key],1)!=b'\1':
            raise ValueError('Supplied states do not show the expected first-blood transition')
    if a.read(x['palette'],64)!=bytes(64) or b.read(x['palette'],64)!=a.read(x['source_palette'],64):
        raise ValueError('Observed post-blood palette does not match the native cached first stage')
    lines=generate(a,x);changed,check=replay(a,lines)
    for address,size in [(x['palette'],64),(x['blood_level_address'],1),(x['bleeding_flag_address'],1)]:
        if changed.read(address,size)!=b.read(address,size):raise ValueError('Replay does not reproduce observed blood data')
    restored=changed.clone()
    for w in check['writes']:restored.write(w['address'],a.read(w['address'],w['bytes']))
    if restored.ram!=a.ram or restored.vram!=a.vram:raise ValueError('Replay changed unrelated memory')
    other=layout(a,3-player)
    if any(changed.read(other[k],1)!=a.read(other[k],1) for k in ('blood_level_address','bleeding_flag_address')):
        raise ValueError('Other player was altered')
    if changed.read(other['palette'],64)!=a.read(other['palette'],64):raise ValueError('Other player palette changed')
    output.mkdir(parents=True)
    text='_S ULUS-10543\n_G WWE SmackDown vs. RAW 2011 [US]\n_C0 Instant Blood P%d - Captured Match TEST\n'%player
    text+=''.join('_L 0x%08X 0x%08X\n'%(first,second) for first,second in lines)
    (output/'ULUS10543-Instant-Blood-TEST.ini').write_text(text)
    report=dict(status='EXPERIMENTAL: offline memory replay verified; live gameplay untested',
        before=am,after=bm,binding={k:hex(v) if k not in ('player','slot') else v for k,v in x.items()},
        verified_native_blood_data=dict(before_level=0,after_level=1,before_bleeding_flag=0,after_bleeding_flag=1,
            pre_blood_palette_all_transparent=True,post_blood_palette_exact_to_cached_first_stage=True),
        replay=check,only_target_blood_records_changed=True,other_player_unchanged=True,
        game_code_pac_and_save_states_modified=False,guard_count=len(lines)-5,
        limitations=['Captured allocation layout only; guards stop it in different layouts.',
            'It holds the initial blood stage while enabled; disable after activation to test progression.',
            'It reproduces blood flags/palette, not every native bleeding callback or statistic.',
            'First Blood may finish when the flag is observed; use a standard match for prolonged viewing.'])
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    assert Path(before_path).read_bytes()==before_bytes and Path(after_path).read_bytes()==after_bytes
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path)
    parser.add_argument('after',type=Path,nargs='?',help='Omit with --snapshot-only')
    parser.add_argument('output',type=Path)
    parser.add_argument('--snapshot-only',action='store_true',help='Use the validated native profile without an observed after state')
    parser.add_argument('--player',type=int,choices=(1,2),required=True)
    args=parser.parse_args()
    if args.snapshot_only:
        if args.after is not None:parser.error('--snapshot-only accepts before and output, without an after state')
        r=run_snapshot(args.before,args.output,args.player)
    else:
        if args.after is None:parser.error('An after state is required unless --snapshot-only is specified')
        r=run(args.before,args.after,args.output,args.player)
    print(r['status'])
