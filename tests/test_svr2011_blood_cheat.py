"""Synthetic RAM/VRAM vectors; no uploaded save state or game image is used."""
import struct
import json
from pathlib import Path
import tempfile
import unittest

from tools.svr2011_blood_cheat import Memory, FINGERPRINT, ACTOR_TABLE, GP, layout, generate, replay, parse_state, offset, validate_activation, run_snapshot


def fixture():
    memory=Memory(bytearray(0x2000000),bytearray(0x200000))
    def w(a,v):memory.write(a,struct.pack('<I',v))
    def h(a,v):memory.write(a,struct.pack('<H',v))
    for a,v in FINGERPRINT.items():w(a,v)
    manager,array,texture_manager,nodes=0x09F00000,0x09F00100,0x09F01000,0x09F01100
    w(GP-0x2D60,manager);w(manager,array)
    w(GP-0x2F68,texture_manager);w(texture_manager+8,nodes);w(texture_manager+0x10,nodes+16)
    for slot in (0,1):
        actor=0x09200000+slot*0x1000;cache=array+slot*0x220;container=0x09F02000+slot*0x100
        entry=container+0x40;texture=0x09F03000+slot*0x100
        cell=0x09F04000+slot*0x100;reader=cell+0x40;header=0x04100000+slot*0x100
        w(ACTOR_TABLE+slot*4,actor);w(actor,0x08CCD3F4);w(actor+0x484,slot);w(actor+0x50,100+slot)
        w(cache+0x18,100+slot);w(cache+4,container);w(cache+0x6C,0)
        w(container+4,entry);w(container+8,1);w(entry,0x10000000+slot)
        w(nodes+slot*8,0x10000000+slot);w(nodes+slot*8+4,texture)
        memory.write(texture+0x10,b'blood\0'.ljust(16,b'\0'))
        w(texture+0x58,cell);w(texture+0x60,0);w(cell,reader);w(reader+0x10,header)
        for a,v in [(4,3),(8,16),(10,1),(12,32),(0x2A,1),(0x2E,1)]:h(header+a,v)
        w(header+0x18,0x30);w(header+0x30,header+0x40)
        memory.write(cache+0x80,bytes([130,22,16,255])*16)
    return Memory(bytes(memory.ram),bytes(memory.vram))


class InstantBloodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.memory=fixture()

    def test_pointer_copy_updates_vram_and_exactly_two_ram_flag_bytes(self):
        m=self.memory;x=layout(m,2);lines=generate(m,x);result,report=replay(m,lines)
        self.assertEqual(report['status'],'offline replay passed')
        self.assertEqual(result.read(x['palette'],64),m.read(x['source_palette'],64))
        self.assertEqual(result.read(x['blood_level_address'],1),b'\1')
        self.assertEqual(result.read(x['bleeding_flag_address'],1),b'\1')
        for address,size in [(x['palette'],64),(x['blood_level_address'],1),(x['bleeding_flag_address'],1)]:
            result.write(address,m.read(address,size))
        self.assertEqual(result.ram,m.ram);self.assertEqual(result.vram,m.vram)

    def test_other_player_and_match_end_field_are_unchanged(self):
        m=self.memory;other=layout(m,1);result,_=replay(m,generate(m,layout(m,2)))
        for key,size in [('palette',64),('blood_level_address',1),('bleeding_flag_address',1)]:
            self.assertEqual(result.read(other[key],size),m.read(other[key],size))
        self.assertEqual(result.u32(0x08CF1DC4),m.u32(0x08CF1DC4))

    def test_changed_actor_palette_pointer_cache_owner_or_code_stops_all_writes(self):
        m=self.memory;x=layout(m,2);lines=generate(m,x)
        for address in [ACTOR_TABLE+4,x['header_cell'],GP-0x2D60,x['cache']+0x18,next(iter(FINGERPRINT))]:
            wrong=m.clone();wrong.write(address,struct.pack('<I',wrong.u32(address)^1))
            result,report=replay(wrong,lines)
            self.assertEqual(report['status'],'guard stopped');self.assertEqual(report['writes'],[])
            self.assertEqual(result.ram,wrong.ram);self.assertEqual(result.vram,wrong.vram)

    def test_replaying_enabled_code_is_idempotent(self):
        m=self.memory;lines=generate(m,layout(m,2));first,_=replay(m,lines);second,_=replay(first,lines)
        self.assertEqual(first.ram,second.ram);self.assertEqual(first.vram,second.vram)

    def test_new_layout_rejects_old_code_and_accepts_regenerated_code(self):
        m=self.memory;old=layout(m,2);old_lines=generate(m,old)
        moved=m.clone();new_actor=old['actor']+0x10000
        moved.write(new_actor,m.read(old['actor'],0x1000))
        moved.write(ACTOR_TABLE+4,struct.pack('<I',new_actor))
        _,stopped=replay(moved,old_lines)
        self.assertEqual(stopped,dict(status='guard stopped',writes=[]))
        binding=layout(moved,2)
        changed,check=validate_activation(moved,binding,generate(moved,binding))
        self.assertEqual(check['status'],'offline replay passed')
        self.assertEqual(changed.read(binding['blood_level_address'],1),b'\1')
        self.assertEqual(changed.read(old['blood_level_address'],1),b'\0')

    def test_single_state_activation_rejects_visible_palette_or_existing_blood(self):
        m=self.memory;x=layout(m,2)
        for key,size in [('palette',64),('blood_level_address',1),('bleeding_flag_address',1)]:
            wrong=m.clone();wrong.write(x[key],bytes([1])*size)
            with self.assertRaises(ValueError):validate_activation(wrong,x,generate(wrong,x))

    def test_single_state_generation_labels_missing_after_evidence_and_preserves_input(self):
        m=self.memory
        raw=b'\0'*40+b'Memory'.ljust(16,b'\0')+struct.pack('<4I',3,1,0x42,len(m.ram))
        raw+=m.ram+struct.pack('<I',0x42)+m.vram+struct.pack('<I',0x42)
        header=struct.pack('<4I',5,0,len(raw),len(raw))+b'v1.20.4\0'.ljust(32,b'\0')+bytes(128)
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'before.ppst';source.write_bytes(header+raw)
            output=Path(root)/'out';report=run_snapshot(source,output,2)
            self.assertIsNone(report['after']);self.assertFalse(report['observed_after_state_comparison'])
            self.assertTrue(report['only_target_blood_records_changed'])
            self.assertEqual(source.read_bytes(),header+raw)
            self.assertEqual(json.loads((output/'report.json').read_text()),report)
            self.assertIn('_C0 Instant Blood P2 - Snapshot Layout TEST',(output/'ULUS10543-Instant-Blood-TEST.ini').read_text())
            with self.assertRaises(FileExistsError):run_snapshot(source,output,2)

    def test_invalid_handle_layout_and_missing_blood_are_rejected(self):
        m=self.memory;x=layout(m,2)
        wrong=m.clone();wrong.write(x['header']+8,struct.pack('<H',256))
        with self.assertRaisesRegex(ValueError,'palette layout'):layout(wrong,2)
        wrong=m.clone();wrong.write(x['cache']+0x6C,bytes.fromhex('ffffffff'))
        with self.assertRaisesRegex(ValueError,'no cached'):layout(wrong,2)
        with self.assertRaisesRegex(ValueError,'Player 1 or Player 2'):layout(m,3)
        with self.assertRaisesRegex(ValueError,'user RAM'):offset(x['palette'])

    def test_bounded_uncompressed_state_reader_and_markers(self):
        m=self.memory
        raw=b'\0'*40+b'Memory'.ljust(16,b'\0')+struct.pack('<4I',3,1,0x42,len(m.ram))
        raw+=m.ram+struct.pack('<I',0x42)+m.vram+struct.pack('<I',0x42)
        header=struct.pack('<4I',5,0,len(raw),len(raw))+b'v1.20.4\0'.ljust(32,b'\0')+b'WWE SVR 2011\0'.ljust(128,b'\0')
        parsed,report=parse_state(header+raw);self.assertEqual(parsed.ram,m.ram);self.assertEqual(parsed.vram,m.vram)
        self.assertFalse(report['source_modified'])
        bad=bytearray(header+raw);bad[176+72+len(m.ram)]=0
        with self.assertRaisesRegex(ValueError,'boundary marker'):parse_state(bad)
        with self.assertRaisesRegex(ValueError,'state header'):parse_state((header+raw)[:-1])

    def test_reader_rejects_wrong_version_and_pointer_commands_outside_emitted_subset(self):
        header=struct.pack('<4I',5,0,1,1)+b'v9.99\0'.ljust(32,b'\0')+bytes(128)+b'X'
        with self.assertRaisesRegex(ValueError,'v1.20.4'):parse_state(header)
        with self.assertRaisesRegex(ValueError,'Truncated pointer copy'):replay(self.memory,[(0x60000000,64)])


if __name__=='__main__':unittest.main()
