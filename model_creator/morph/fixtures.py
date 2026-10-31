"""Original block geometry with anatomically spaced test anchors; no game asset."""
import struct

from model_creator.fixtures import pair
from tools.psp_mesh_merge_trial import sections
from tools.pac_repack import replace_sections
from model_creator.native import audit_yobj


def donor():
    pac=pair()[0];raw=bytearray(next(r for s,r in sections(pac) if s['id']==2));model=audit_yobj(raw)
    start=next(a['start'] for a in model['report']['allocations'] if a['kind']=='bone table')
    positions={'koshi':(0,-1,0),'mune':(0,-4,0),'kubi':(0,-2,0),'atama':(0,-1.5,0)}
    for side,sign in (('l_',1),('r_',-1)):
        positions.update({side+'sakotsu':(sign*1.5,-.4,0),side+'ninoude':(sign,0,0),
                          side+'kote':(sign*1.5,0,0),side+'te':(sign,0,0),
                          side+'momo':(sign*.7,1,0),side+'sune':(0,3.5,0),side+'ashi':(0,3.5,0)})
    for b in model['bones']:
        struct.pack_into('<3f',raw,start+b['index']*80+16,*positions.get(b['name'],(0,0,0)))
    return replace_sections(pac,{2:bytes(raw)})
