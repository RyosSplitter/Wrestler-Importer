"""Independent read-only source/IR position-scale audit, before rig adaptation.

Verify stored fixed-point bytes against each packet's binary-point field. The
comparison reference must not silently inherit the decoder's own scale bug.
No vertex welding, re-rigging or positional correction is performed here.
"""
import struct
import numpy as np
from tools.wwe13_inspect import checked
from tools.wwe13_wii_corpus import bundles


def verify(data,index,model):
    found=bundles(data)
    if type(index)is not int or not 0<=index<len(found):raise ValueError('Invalid source encoding audit costume')
    payloads={s['id']:s['raw'] for s in found[index]['sections'] if s['raw'].startswith(b'DUMY')}
    packets={};counts={};position_indices={}
    for sid,payload in payloads.items():
        raw=payload[24:];end=struct.unpack('>I',checked(raw,4,4))[0]+8;raw=checked(raw,0,end)
        count=struct.unpack('>I',checked(raw,56,4))[0]
        if count not in (1,2):raise ValueError('Unobserved source encoding packet count')
        for packet in range(count):
            h=64+64*packet;fraction=checked(raw,h+52,1)[0]
            if fraction not in (7,8):raise ValueError('Unobserved position fraction bits in source encoding audit')
            n=struct.unpack('>H',checked(raw,h+8,2))[0]
            address=struct.unpack('>I',checked(raw,h+20,4))[0]+8
            positions=np.frombuffer(checked(raw,address,n*12),dtype='>i2').reshape(n,6)[:,:3].astype(float)/(2**fraction)
            key=(sid,packet);packets[key]=(positions,fraction);counts[key]=0;position_indices[key]=set()
    for mesh in model['meshes']:
        key=(mesh['source_section'],mesh.get('source_packet',0))
        if key not in packets:raise ValueError('Source mesh has no encoding audit packet')
        positions,fraction=packets[key]
        for vertex in mesh['vertices']:
            i=vertex['source_position_index']
            if type(i)is not int or not 0<=i<len(positions):raise ValueError('Source IR position index outside encoded buffer')
            if not np.array_equal(np.asarray(vertex['position']),positions[i]):
                raise ValueError('Source position-scale mismatch in section %d packet %d record %d (Q%d)'%(*key,i,fraction))
            counts[key]+=1;position_indices[key].add(i)
    if not counts or any(n==0 for n in counts.values()):raise ValueError('Source encoding audit found an unaudited model packet')
    return dict(status='pass',packets=[dict(section=sid,packet=packet,position_fraction_bits=packets[sid,packet][1],
        position_divisor=2**packets[sid,packet][1],vertex_records_checked=counts[sid,packet],
        unique_positions_checked=len(position_indices[sid,packet]),fraction_byte_offset_from_yobj=64+64*packet+52)
        for sid,packet in packets],
        policy='Exact original fixed-point buffer / per-packet binary-point field versus source IR before rigging and reference QA',
        limitation='Checks decoder compliance with the observed Q7/Q8 contract; does not emulate source shaders or animation.')
