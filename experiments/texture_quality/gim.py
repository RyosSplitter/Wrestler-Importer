"""Research-only decoder for observed native padded narrow indexed GIMs.

Never changes the production writer/reader. The native pitch interpretation is
supported by header/allocation evidence and tests against the existing subset.
"""
import struct
import numpy as np


def read_native_gim(data):
    if len(data)<128 or data[:12]!=b'MIG.00.1PSP\0':raise ValueError('Missing GIM signature')
    if struct.unpack_from('<I',data,20)[0]+16!=len(data):raise ValueError('GIM root length mismatch')
    fmt,order,width,height,bits=struct.unpack_from('<5H',data,68)
    if (fmt,bits) not in ((4,4),(5,8)) or order!=1 or not width or not height:raise ValueError('Unsupported native image format')
    if width&(width-1) or height&(height-1):raise ValueError('Non-power-of-two native dimensions')
    block_size=struct.unpack_from('<I',data,52)[0];palette_start=48+block_size
    if palette_start+80>len(data):raise ValueError('Palette outside allocation')
    pformat,porder,pwidth,pheight,pbits=struct.unpack_from('<5H',data,palette_start+20)
    if (pformat,porder,pbits,pwidth,pheight)!=(3,0,32,1<<bits,1):raise ValueError('Unsupported native palette contract')
    start=64+struct.unpack_from('<I',data,92)[0]
    row_bytes=((width*bits+7)//8+15)//16*16;padded_height=(height+7)//8*8
    if start<128 or start+row_bytes*padded_height!=palette_start:raise ValueError('Native padded image allocation mismatch')
    if palette_start+struct.unpack_from('<I',data,palette_start+4)[0]!=len(data):raise ValueError('Palette length mismatch')
    if len(data)-(palette_start+80)!=(1<<bits)*4:raise ValueError('Palette color count mismatch')
    yy,xx=np.indices((padded_height,row_bytes))
    address=((yy//8)*(row_bytes//16)+xx//16)*128+(yy%8)*16+xx%16
    packed=np.frombuffer(data[start:palette_start],dtype=np.uint8)[address]
    if bits==8:indices=packed[:height,:width].copy()
    else:
        indices=np.empty((padded_height,row_bytes*2),dtype=np.uint8)
        indices[:,::2]=packed&15;indices[:,1::2]=packed>>4
        indices=indices[:height,:width].copy()
    palette=np.frombuffer(data[palette_start+80:],dtype=np.uint8).reshape(1<<bits,4).copy()
    return indices,palette
